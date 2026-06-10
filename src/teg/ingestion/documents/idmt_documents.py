"""Build the Cosmos IDMT/ER document and the Cosmos Theme documents.

Single source of truth for these two shapes (TDD 4.1-4.3 ER, 4.4-4.5 Theme). The ER is a
root (no parent); each Theme points at its ER via parentId. Source created/modified live
on the envelope; ER business context comes from condense, theme GT from resolution +
direct/implied classification.
"""

from __future__ import annotations

from teg.domain.condensed import CondensedTicket
from teg.ingestion.extraction.jira_records import ExtractedEngagementRequest, ExtractedTheme
from teg.ingestion.ground_truth.theme_ground_truth import ThemeGroundTruth

ER_SOURCE = "Jira"
ER_ENTITY_TYPE = "EngagementRequest"
THEME_ENTITY_TYPE = "Theme"


def build_idmt_document(
    *,
    er: ExtractedEngagementRequest,
    condensed: CondensedTicket,
    theme_gt: list[ThemeGroundTruth],
) -> dict:
    """Cosmos IDMT/ER document: condensed business context + theme ground truth."""
    fields = condensed.summary_fields
    return {
        "id": er.stable_id,
        "source": ER_SOURCE,
        "entityType": ER_ENTITY_TYPE,
        "sourceId": er.key or None,  # IDMT-#### (mutable Jira key)
        "createdDate": er.created_date or None,
        "createdBy": er.created_by or None,
        "modifiedDate": er.modified_date or None,
        "modifiedBy": None,
        "properties": {
            "description": condensed.description,
            "summary": fields.generated_summary,
            "title": condensed.ticket_title or er.title,
            "rawText": condensed.raw_text,
            "keyTerms": list(fields.key_terms),
            "businessProblem": fields.business_problem,
            "businessCapability": fields.business_capability,
            "stakeholders": list(fields.stakeholders),
            "systemsAndProducts": list(fields.systems_and_products),
            # Store the full condense output so historic tickets can skip condense on
            # replay - the 18 generation signals feed Theme Description + Business Needs.
            "generationSignals": condensed.generation_signals.model_dump(by_alias=True),
            "themes": [_theme_gt(gt) for gt in theme_gt],
        },
    }


def _theme_gt(gt: ThemeGroundTruth) -> dict:
    return {
        "key": gt.theme_stable_id,
        "groupId": gt.group_key,
        "valueStreamId": gt.value_stream_id,
        "valueStreamName": gt.value_stream_name,
    }


def build_theme_document(theme: ExtractedTheme, *, parent_er_id: str) -> dict:
    """Cosmos Theme document: the Jira GROUP artifact, linked to its ER via parentId."""
    return {
        "id": theme.stable_id,
        "source": ER_SOURCE,
        "entityType": THEME_ENTITY_TYPE,
        "groupId": theme.group_key or None,  # GROUP-#### (mutable Jira key)
        "parentId": parent_er_id,
        "parentEntityType": ER_ENTITY_TYPE,
        "createdDate": theme.created_date or None,
        "createdBy": theme.created_by or None,
        "modifiedDate": theme.modified_date or None,
        "modifiedBy": None,
        "properties": {
            "description": theme.description,
            "title": theme.summary,
        },
    }
