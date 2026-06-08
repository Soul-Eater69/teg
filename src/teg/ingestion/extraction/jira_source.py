"""Fetch an Engagement Request and its linked Themes from Jira (ingestion).

Parsing (pure, from raw issue JSON) is separated from fetching (httpx) so the mapping
is unit-testable. Linked themes = GROUP-keyed issues in the ER's issuelinks; each GROUP
is fetched once to get its stable id + description + dates (the link alone lacks those).
"""

from __future__ import annotations

from dataclasses import replace

import httpx

from teg.config.settings import Settings
from teg.ingestion.extraction.jira_records import ExtractedEngagementRequest, ExtractedTheme

# Jira issue fields we request (the REST `fields` param is a comma-joined list).
_COMMON_FIELDS = ("summary", "description", "created", "updated", "reporter")
_ER_FIELDS = (*_COMMON_FIELDS, "issuelinks")  # the ER also needs its linked themes
_THEME_FIELDS = _COMMON_FIELDS


def _text(value: object) -> str:
    return str(value or "").strip()


def _actor(fields: dict) -> str:
    reporter = fields.get("reporter")
    if isinstance(reporter, dict):
        return _text(reporter.get("name") or reporter.get("key") or reporter.get("displayName"))
    return ""


def _is_theme_issue(issue: dict) -> bool:
    issuetype = (issue.get("fields") or {}).get("issuetype") or {}
    return "theme" in str(issuetype.get("name") or "").lower()


def _is_implementation_link(link_type: dict) -> bool:
    """An 'implement*' link (inward 'is implemented by' / outward 'implements')."""
    phrases = (link_type.get("inward"), link_type.get("outward"), link_type.get("name"))
    return any("implement" in str(phrase or "").lower() for phrase in phrases)


def _linked_theme_keys(fields: dict) -> list[str]:
    """Keys of linked Theme issues.

    A theme link is an implementation-style link whose linked issue is a Theme. Each
    issuelink carries only one end (inwardIssue or outwardIssue - the other side is the
    ER itself), so we take whichever is present; non-Theme issues on the same link type
    (e.g. '... - BO') are skipped, and keys are deduped.
    """
    keys: list[str] = []
    for link in fields.get("issuelinks") or []:
        if not _is_implementation_link(link.get("type") or {}):
            continue
        issue = link.get("inwardIssue") or link.get("outwardIssue")
        if isinstance(issue, dict) and _is_theme_issue(issue):
            key = _text(issue.get("key"))
            if key and key not in keys:
                keys.append(key)
    return keys


def parse_engagement_request(issue: dict) -> tuple[ExtractedEngagementRequest, list[str]]:
    """Return the ER (without theme bodies) plus the linked Theme keys to fetch."""
    fields = issue.get("fields") or {}
    er = ExtractedEngagementRequest(
        stable_id=_text(issue.get("id")),
        key=_text(issue.get("key")),
        title=_text(fields.get("summary")),
        description=_text(fields.get("description")),
        created_date=_text(fields.get("created")),
        modified_date=_text(fields.get("updated")),
        created_by=_actor(fields),
    )
    return er, _linked_theme_keys(fields)


def parse_theme(issue: dict) -> ExtractedTheme:
    fields = issue.get("fields") or {}
    return ExtractedTheme(
        stable_id=_text(issue.get("id")),
        group_key=_text(issue.get("key")),
        summary=_text(fields.get("summary")),
        description=_text(fields.get("description")),
        created_date=_text(fields.get("created")),
        modified_date=_text(fields.get("updated")),
        created_by=_actor(fields),
    )


class JiraIngestionSource:
    def __init__(self, http_client: httpx.AsyncClient, *, api_version: str = "2") -> None:
        self._http = http_client
        self._api_version = api_version

    async def fetch_engagement_request(self, ticket_id: str) -> ExtractedEngagementRequest:
        er, group_keys = parse_engagement_request(await self._issue(ticket_id, _ER_FIELDS))
        themes = [parse_theme(await self._issue(key, _THEME_FIELDS)) for key in group_keys]
        return replace(er, themes=themes)

    async def _issue(self, issue_id: str, fields: tuple[str, ...]) -> dict:
        response = await self._http.get(
            f"/rest/api/{self._api_version}/issue/{issue_id}",
            params={"fields": ",".join(fields)},
        )
        response.raise_for_status()
        return response.json() or {}


def build_jira_ingestion_source(settings: Settings) -> JiraIngestionSource:
    http_client = httpx.AsyncClient(
        base_url=settings.jira_base_url,
        headers={"Authorization": f"Bearer {settings.jira_token}"},
        timeout=settings.jira_timeout_seconds,
        verify=settings.jira_verify_ssl,
    )
    return JiraIngestionSource(http_client, api_version=settings.jira_api_version)
