"""Build the Cosmos VS-catalogue document and the VS search-index document.

Single source of truth for these two shapes (TDD 4.6-4.8 Cosmos catalogue, 4.11-4.12
VS index). The Cosmos doc is the governed system of record with the full stage
hierarchy; the index doc carries only retrieval text + vector + display/filter fields.
"""

from __future__ import annotations

from teg.ingestion.catalogues.models import CatalogueStage, CatalogueValueStream

CATALOGUE_SOURCE = "Sightline"
ENTITY_TYPE = "valueStream"


def build_catalogue_document(vs: CatalogueValueStream) -> dict:
    """Cosmos governed-catalogue document (point-read by valueStreamId at stage gen)."""
    return {
        "id": vs.value_stream_id,
        "source": CATALOGUE_SOURCE,
        "entityType": ENTITY_TYPE,
        "parentId": None,
        "parentEntityType": None,
        "createdAt": vs.value_stream_created_date or None,
        "createdBy": None,
        "modifiedAt": None,
        "modifiedBy": None,
        "properties": {
            "valueStreamId": vs.value_stream_id,
            "valueStreamName": vs.value_stream_name,
            "valueStreamDescription": vs.value_stream_description,
            "valueStreamCategory": vs.value_stream_category,
            "valueStreamTrigger": vs.value_stream_trigger,
            "valueStreamStakeholders": list(vs.value_stream_stakeholders),
            "valueStages": [_stage_document(stage) for stage in vs.stages],
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
    vs: CatalogueValueStream, content_vector: list[float] | None = None
) -> dict:
    """VS search-index document: retrieval text + vector + display/filter fields only."""
    return {
        "id": vs.value_stream_id,
        "source": CATALOGUE_SOURCE,
        "entityType": ENTITY_TYPE,
        "createdAt": vs.value_stream_created_date or None,
        "createdBy": None,
        "modifiedAt": None,
        "modifiedBy": None,
        "content": build_catalogue_content(vs),
        "content_vector": content_vector,
        "properties": {
            "valueStreamId": vs.value_stream_id,
            "valueStreamName": vs.value_stream_name,
            "valueStreamDescription": vs.value_stream_description,
            "valueStreamCategory": vs.value_stream_category,
        },
    }
