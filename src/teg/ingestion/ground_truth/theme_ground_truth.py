"""Resolved theme ground-truth record.

One per linked Theme after VS resolution (theme summary -> approved catalogue VS) and
direct/implied classification. This is what becomes an entry in the ER's
``properties.themes[]`` (and links to the Theme doc via ``theme_stable_id``).
"""

from __future__ import annotations

from dataclasses import dataclass

from teg.domain.value_stream import SupportType


@dataclass(frozen=True)
class ThemeGroundTruth:
    theme_stable_id: str  # -> Theme doc id (themes[].key)
    group_key: str  # GROUP-#### (themes[].groupId)
    value_stream_id: str  # resolved approved VS id
    value_stream_name: str  # resolved canonical VS name
    support_type: SupportType  # direct | implied
    reason: str = ""
    evidence: str = ""
