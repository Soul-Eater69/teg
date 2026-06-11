"""Build the Cosmos IDMT/ER document and the Cosmos Theme documents.

Single source of truth for these two shapes. The ER is a root (no parent); each Theme points
at its ER via parentId. Level-1 fields are the Cosmos document's own lifecycle (id, ingestedDate);
the SOURCE ticket's audit (created/modified by/date) lives inside properties alongside the rest of
the business data. id is the stable Jira internal issue id (deterministic -> idempotent upsert);
ticketId is the mutable business key (IDMT-####).
"""

from __future__ import annotations

from datetime import datetime, timezone

from teg.domain.condensed import CondensedTicket
from teg.ingestion.extraction.jira_records import ExtractedEngagementRequest, ExtractedTheme
from teg.ingestion.ground_truth.theme_ground_truth import ThemeGroundTruth

ER_SOURCE = "Jira"
ER_ENTITY_TYPE = "EngagementRequest"  # PascalCase (consistent with ValueStream)
THEME_ENTITY_TYPE = "Theme"
INGEST_ACTOR = "teg-ingestion"  # the Cosmos createdBy/lastModifiedBy actor


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_idmt_document(
    *,
    er: ExtractedEngagementRequest,
    condensed: CondensedTicket,
    theme_gt: list[ThemeGroundTruth],
) -> dict:
    """Cosmos IDMT/ER document (TDD 4.1.1). Level-1 = Cosmos lifecycle; the source ticket's own
    dates live in properties as creationDate/insightsTime."""
    fields = condensed.summary_fields
    now = _now()
    return {
        "id": er.stable_id,  # Cosmos doc id = the stable Jira internal id
        "key": er.key or None,  # IDMT-#### (mutable business key)
        "sourceId": er.stable_id,  # stable Jira internal id (== id)
        "source": ER_SOURCE,
        "entityType": ER_ENTITY_TYPE,
        "createdAt": now,  # Cosmos lifecycle
        "createdBy": INGEST_ACTOR,
        "lastModifiedAt": now,
        "lastModifiedBy": INGEST_ACTOR,
        "parentRef": None,  # ER is a root - no parent
        "properties": {
            "description": condensed.description,
            "summary": condensed.ticket_title or er.title,  # the ticket TITLE
            "creationDate": er.created_date or None,  # source ticket created
            "insightsTime": er.modified_date or None,  # source ticket last updated
            "businessSummary": fields.generated_summary,  # LLM-generated summary
            "keyTerms": list(fields.key_terms),
            "businessProblem": fields.business_problem,
            "businessCapability": fields.business_capability,
            "stakeholders": list(fields.stakeholders),
            "systemsAndProducts": list(fields.systems_and_products),
            "rawText": condensed.raw_text,
            # Value Stream ground truth (one entry per linked theme).
            "themes": [_theme_gt(gt) for gt in theme_gt],
        },
    }


def _theme_gt(gt: ThemeGroundTruth) -> dict:
    return {
        "key": gt.group_key,  # GROUP-#### (business key)
        "sourceId": gt.theme_stable_id,  # stable Jira theme id -> Theme doc id
        "valueStreamId": gt.value_stream_id,
        "valueStreamName": gt.value_stream_name,
    }


def build_theme_document(theme: ExtractedTheme, *, parent_er_id: str) -> dict:
    """Cosmos Theme document (TDD 4.1.2): the Jira GROUP artifact, linked to its ER via parentRef."""
    now = _now()
    return {
        "id": theme.stable_id,  # Cosmos doc id = stable Jira internal id
        "key": theme.group_key or None,  # GROUP-#### (mutable business key)
        "sourceId": theme.stable_id,  # stable Jira internal id (== id)
        "source": ER_SOURCE,
        "entityType": THEME_ENTITY_TYPE,
        "createdAt": now,  # Cosmos lifecycle
        "createdBy": INGEST_ACTOR,
        "lastModifiedAt": now,
        "lastModifiedBy": INGEST_ACTOR,
        "parentRef": parent_er_id,  # the parent ER's sourceId (stable Jira id)
        "properties": {
            "summary": theme.summary,  # ISSUE title
            "description": theme.description,
            "valueStream": {
                "valueStreamId": theme.value_stream_id,
                "valueStreamName": theme.value_stream_name,
            },
            "creationDate": theme.created_date or None,  # source created
            "insightsTime": theme.modified_date or None,  # source last updated
        },
    }
