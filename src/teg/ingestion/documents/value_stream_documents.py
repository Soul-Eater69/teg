"""Build the Cosmos VS-catalogue document and the VS search-index document.

Single source of truth for these two shapes (TDD 4.6-4.8 Cosmos catalogue, 4.11-4.12
VS index). The Cosmos doc is the governed system of record with the full stage
hierarchy; the index doc carries only retrieval text + vector + display/filter fields.
"""

from __future__ import annotations

from datetime import datetime, timezone

from teg.ingestion.catalogues.models import CatalogueStage, CatalogueValueStream

CATALOGUE_SOURCE = "Sightline"
ENTITY_TYPE = "valueStream"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_catalogue_document(vs: CatalogueValueStream, *, ingested_at: str | None = None) -> dict:
    """Cosmos governed-catalogue document (point-read by valueStreamId at stage gen).

    The envelope carries ``ingestedAt`` (our write time); the source catalogue date
    lives in ``properties.createdDate``.
    """
    return {
        "id": vs.value_stream_id,
        "source": CATALOGUE_SOURCE,
        "entityType": ENTITY_TYPE,
        "parentId": None,
        "parentEntityType": None,
        "ingestedAt": ingested_at or _utc_now(),
        "properties": {
            "valueStreamId": vs.value_stream_id,
            "valueStreamName": vs.value_stream_name,
            "valueStreamDescription": vs.value_stream_description,
            "valueStreamCategory": vs.value_stream_category,
            "valueStreamTrigger": vs.value_stream_trigger,
            "valueStreamStakeholders": list(vs.value_stream_stakeholders),
            "valueStages": [_stage_document(stage) for stage in vs.stages],
            "createdDate": vs.value_stream_created_date or None,
        },
    }


def _stage_document(stage: CatalogueStage) -> dict:
    return {
        "stageId": stage.stage_id,
        "stageSequence": stage.stage_sequence,
        "stageName": stage.stage_name,
        "stageDisplayName": stage.stage_display_name,
        "stageDescription": stage.stage_description,
        "stageEntranceCriteria": stage.stage_entrance_criteria,
        "stageExitCriteria": stage.stage_exit_criteria,
        "stageValueItems": stage.stage_value_items,
        "stageStakeholders": list(stage.stage_stakeholders),
    }


def build_catalogue_content(vs: CatalogueValueStream) -> str:
    """Retrieval text embedded for the VS index: name + description + category + trigger."""
    parts = [
        vs.value_stream_name,
        vs.value_stream_description,
        vs.value_stream_category,
        vs.value_stream_trigger,
    ]
    return "\n".join(part for part in parts if part and part.strip())


def build_index_document(
    vs: CatalogueValueStream,
    content_vector: list[float] | None = None,
    *,
    ingested_at: str | None = None,
) -> dict:
    """VS search-index document: retrieval text + vector + display/filter fields only."""
    return {
        "id": vs.value_stream_id,
        "source": CATALOGUE_SOURCE,
        "entityType": ENTITY_TYPE,
        "ingestedAt": ingested_at or _utc_now(),
        "content": build_catalogue_content(vs),
        "content_vector": content_vector,
        "properties": {
            "valueStreamId": vs.value_stream_id,
            "valueStreamName": vs.value_stream_name,
            "valueStreamDescription": vs.value_stream_description,
            "valueStreamCategory": vs.value_stream_category,
        },
    }
