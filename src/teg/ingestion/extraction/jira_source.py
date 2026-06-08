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

_ER_FIELDS = "summary,description,created,updated,reporter,issuelinks"
_THEME_FIELDS = "summary,description,created,updated,reporter"


def _text(value: object) -> str:
    return str(value or "").strip()


def _actor(fields: dict) -> str:
    reporter = fields.get("reporter")
    if isinstance(reporter, dict):
        return _text(reporter.get("name") or reporter.get("key") or reporter.get("displayName"))
    return ""


def _linked_group_keys(fields: dict) -> list[str]:
    """GROUP-keyed linked issues from both inward and outward links (themes)."""
    keys: list[str] = []
    for link in fields.get("issuelinks") or []:
        for side in ("inwardIssue", "outwardIssue"):
            issue = link.get(side)
            if not isinstance(issue, dict):
                continue
            key = _text(issue.get("key"))
            if key.upper().startswith("GROUP") and key not in keys:
                keys.append(key)
    return keys


def parse_engagement_request(issue: dict) -> tuple[ExtractedEngagementRequest, list[str]]:
    """Return the ER (without theme bodies) plus the linked GROUP keys to fetch."""
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
    return er, _linked_group_keys(fields)


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

    async def _issue(self, issue_id: str, fields: str) -> dict:
        response = await self._http.get(
            f"/rest/api/{self._api_version}/issue/{issue_id}", params={"fields": fields}
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
