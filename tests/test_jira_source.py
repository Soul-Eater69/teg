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
            {
                "type": {"name": "Implement", "inward": "is implemented by", "outward": "implements"},
                "inwardIssue": {
                    "id": "3966046",
                    "key": "GROUP-23618",
                    "fields": {"summary": "... : Appeal Decision", "issuetype": {"name": "Theme"}},
                },
            },
            {  # implementation link but NOT a Theme issuetype -> excluded (the "- BO" case)
                "type": {"name": "Implement", "inward": "is implemented by", "outward": "implements"},
                "inwardIssue": {
                    "id": "9999",
                    "key": "GROUP-22287",
                    "fields": {"summary": "... - BO", "issuetype": {"name": "Business Outcome"}},
                },
            },
            {  # non-implementation link -> excluded
                "type": {"name": "Estimate", "inward": "is estimated by", "outward": "estimates"},
                "inwardIssue": {
                    "id": "3575756",
                    "key": "IDMT-27092",
                    "fields": {"summary": "y", "issuetype": {"name": "Engagement Request"}},
                },
            },
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
    # only the Theme-typed implementation link; the '- BO' (non-Theme) and the
    # 'is estimated by' (non-implementation) links are excluded
    assert group_keys == ["GROUP-23618"]


def test_parse_theme() -> None:
    theme = parse_theme(THEME_ISSUE)
    assert theme.stable_id == "3966046" and theme.group_key == "GROUP-23618"
    assert theme.summary.endswith("Appeal Decision")
    assert theme.created_by == "U447949"
    assert theme.modified_date.startswith("2025-11-10")
