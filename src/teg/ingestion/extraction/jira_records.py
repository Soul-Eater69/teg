"""Extracted Jira records for ingestion (ER + its linked Themes).

The doc `id` is the STABLE Jira internal issue id; the mutable Jira key (IDMT-####,
GROUP-####) is kept separately. A linked Theme's stable id + content come from fetching
the GROUP issue (the issuelink only gives the key), so we build the Theme doc from the
same fetch.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedTheme:
    """A linked Theme / GROUP issue."""

    stable_id: str  # Jira internal issue id (e.g. 3966046)
    group_key: str  # GROUP-#### (mutable)
    summary: str  # GROUP summary - the Theme title; also encodes the value stream name
    description: str = ""
    created_date: str = ""
    modified_date: str = ""
    created_by: str = ""


@dataclass(frozen=True)
class ExtractedEngagementRequest:
    """An IDMT Engagement Request and its linked themes."""

    stable_id: str  # Jira internal issue id (e.g. 3364549)
    key: str  # IDMT-#### (mutable)
    title: str  # Jira summary
    description: str = ""
    created_date: str = ""
    modified_date: str = ""
    created_by: str = ""
    themes: list[ExtractedTheme] = field(default_factory=list)
