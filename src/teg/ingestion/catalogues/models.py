"""Parsed Sightline Value Stream catalogue records (value_stream_stage_map.json).

Clean domain records for the approved 50-VS catalogue. The semicolon-delimited
stakeholder strings in the source are normalised to lists here.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CatalogueStage:
    stage_id: str
    stage_sequence: int
    stage_name: str
    stage_display_name: str
    stage_description: str
    stage_entrance_criteria: str
    stage_exit_criteria: str
    stage_value_items: str
    stage_stakeholders: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CatalogueValueStream:
    value_stream_id: str
    value_stream_name: str
    value_stream_description: str
    value_stream_category: str
    value_stream_trigger: str
    value_stream_created_date: str
    value_stream_stakeholders: list[str] = field(default_factory=list)
    stages: list[CatalogueStage] = field(default_factory=list)
