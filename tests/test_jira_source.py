"""Jira ingestion parsing: ER + linked-theme extraction from raw issue JSON."""

from __future__ import annotations

from teg.ingestion.extraction.jira_source import parse_engagement_request, parse_theme

ER_ISSUE = {
    "id": "3364549",
    "key": "IDMT-19761",
    "fields": {
        "summary": "CP 2026 Women's and Family Health",
        "description": "Gate 0 link and idea card",
        "created": "2024-05-31T08:12:12.023-0500",
        "updated": "2025-12-31T09:47:10.733-0600",
        "reporter": {"name": "U133178", "displayName": "Lisa Yancey"},
        "issuelinks": [
            {"outwardIssue": {"id": "3966046", "key": "GROUP-23618", "fields": {"summary": "x"}}},
            {"inwardIssue": {"id": "3575756", "key": "IDMT-27092", "fields": {"summary": "y"}}},
        ],
    },
}

THEME_ISSUE = {
    "id": "3966046",
    "key": "GROUP-23618",
    "fields": {
        "summary": "CP 2027 Guided Health Plans : Appeal Decision",
        "description": "This theme describes the processed appeal",
        "created": "2025-07-09T12:55:24.147-0500",
        "updated": "2025-11-10T11:49:11.773-0600",
        "reporter": {"name": "U447949"},
    },
}


def test_parse_engagement_request_and_group_links() -> None:
    er, group_keys = parse_engagement_request(ER_ISSUE)
    assert er.stable_id == "3364549" and er.key == "IDMT-19761"
    assert er.title.startswith("CP 2026")
    assert er.created_by == "U133178"
    assert group_keys == ["GROUP-23618"]  # only GROUP-keyed links, not the IDMT link


def test_parse_theme() -> None:
    theme = parse_theme(THEME_ISSUE)
    assert theme.stable_id == "3966046" and theme.group_key == "GROUP-23618"
    assert theme.summary.endswith("Appeal Decision")
    assert theme.created_by == "U447949"
    assert theme.modified_date.startswith("2025-11-10")
