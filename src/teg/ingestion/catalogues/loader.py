"""Load and parse the Sightline VS catalogue (value_stream_stage_map.json).

The map is VS -> stages (no L2/L3 - that comes from a separate source). Stakeholder
fields are semicolon-delimited strings in the source; we split them to lists.
"""

from __future__ import annotations

import json
from pathlib import Path

from teg.ingestion.catalogues.models import CatalogueStage, CatalogueValueStream


def load_value_stream_catalogue(path: str | Path) -> list[CatalogueValueStream]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [_value_stream(raw) for raw in data.get("value_streams") or []]


def _value_stream(raw: dict) -> CatalogueValueStream:
    return CatalogueValueStream(
        value_stream_id=_text(raw.get("value_stream_id")),
        value_stream_name=_text(raw.get("value_stream_name")),
        value_stream_description=_text(raw.get("value_stream_description")),
        value_stream_category=_text(raw.get("value_stream_category")),
        value_stream_trigger=_text(raw.get("value_stream_trigger")),
        value_stream_created_date=_text(raw.get("value_stream_created_date")),
        value_stream_stakeholders=_split(raw.get("value_stream_stakeholders")),
        stages=[_stage(s) for s in raw.get("stages") or []],
    )


def _stage(raw: dict) -> CatalogueStage:
    return CatalogueStage(
        stage_id=_text(raw.get("stage_id")),
        stage_sequence=_int(raw.get("stage_sequence")),
        stage_name=_text(raw.get("stage_name")),
        stage_display_name=_text(raw.get("stage_display_name")),
        stage_description=_text(raw.get("stage_description")),
        stage_entrance_criteria=_text(raw.get("stage_entrance_criteria")),
        stage_exit_criteria=_text(raw.get("stage_exit_criteria")),
        stage_value_items=_text(raw.get("stage_value_items")),
        stage_stakeholders=_split(raw.get("stage_stakeholders")),
    )


def _text(value: object) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _split(raw: object) -> list[str]:
    """Split a semicolon-delimited source string (or pass a list through), trimmed."""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else str(raw).split(";")
    return [text for text in (" ".join(str(item).split()) for item in items) if text]
