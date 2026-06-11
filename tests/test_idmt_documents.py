"""IDMT/ER + Theme Cosmos document builders (Generator B doc shapes)."""

from __future__ import annotations

from teg.domain.condensed import CondensedTicket, GenerationSignals, SummaryFields
from teg.ingestion.documents.idmt_documents import build_idmt_document, build_theme_document
from teg.ingestion.extraction.jira_records import ExtractedEngagementRequest, ExtractedTheme
from teg.ingestion.ground_truth.theme_ground_truth import ThemeGroundTruth


def _condensed() -> CondensedTicket:
    return CondensedTicket(
        ticket_id="IDMT-19761",
        ticket_title="CP 2026 Women's and Family Health",
        primary_source="idea_card",
        summary_fields=SummaryFields(
            generated_summary="Automate appeals handling",
            business_problem="Manual appeals are slow",
            business_capability="Faster appeal resolution",
            key_terms=["appeals", "Medicare"],
            stakeholders=["Claims Ops"],
            systems_and_products=["Salesforce"],
        ),
        generation_signals=GenerationSignals(),
        description="Gate 0 link and idea card",
        raw_text="full consolidated text",
    )


def _er() -> ExtractedEngagementRequest:
    return ExtractedEngagementRequest(
        stable_id="3364549",
        key="IDMT-19761",
        title="CP 2026 Women's and Family Health",
        created_date="2024-05-31T08:12:12-05:00",
        modified_date="2025-12-31T09:47:10-06:00",
        created_by="U133178",
        themes=[],
    )


def test_idmt_document_shape() -> None:
    gt = [
        ThemeGroundTruth(
            theme_stable_id="3966046",
            group_key="GROUP-23618",
            value_stream_id="VSR00074590",
            value_stream_name="Resolve Appeal",
        )
    ]
    doc = build_idmt_document(er=_er(), condensed=_condensed(), theme_gt=gt)
    assert doc["id"] == "3364549"  # stable Jira id = the ticket's unique id
    assert doc["ticketId"] == "IDMT-19761"  # mutable business key (was sourceId)
    assert doc["entityType"] == "EngagementRequest"
    assert doc["ingestedDate"]  # level-1 Cosmos lifecycle timestamp present
    assert "parentId" not in doc  # ER is a root
    props = doc["properties"]
    # source ticket audit moved into properties (level-1 is Cosmos lifecycle)
    assert props["createdBy"] == "U133178"
    assert "createdDate" in props and "modifiedDate" in props
    assert "createdBy" not in doc  # no longer at top level
    assert props["summary"] == "Automate appeals handling"
    assert props["businessProblem"] == "Manual appeals are slow"
    assert props["keyTerms"] == ["appeals", "Medicare"]
    assert "marketSegments" in props["generationSignals"]  # full condense output stored
    theme = props["themes"][0]
    assert theme["key"] == "3966046"  # -> Theme doc id
    assert theme["groupId"] == "GROUP-23618"
    assert theme["valueStreamId"] == "VSR00074590"
    assert theme["valueStreamName"] == "Resolve Appeal"
    assert "supportType" not in theme and "evidence" not in theme  # classification removed


def test_theme_document_shape() -> None:
    theme = ExtractedTheme(
        stable_id="3966046",
        group_key="GROUP-23618",
        summary="CP 2027 Guided Health Plans : Appeal Decision",
        description="This theme describes the processed appeal",
        created_date="2025-07-09T12:55:24-05:00",
        modified_date="2025-11-10T11:49:11-06:00",
        created_by="U447949",
    )
    doc = build_theme_document(theme, parent_er_id="3364549")
    assert doc["id"] == "3966046"  # stable Jira id
    assert doc["groupId"] == "GROUP-23618"  # mutable GROUP key
    assert doc["entityType"] == "Theme"
    assert doc["parentId"] == "3364549"  # links to its ER
    assert doc["parentEntityType"] == "EngagementRequest"
    assert doc["ingestedDate"]  # level-1 Cosmos lifecycle
    assert doc["properties"]["createdBy"] == "U447949"  # source audit moved into properties
    assert "createdBy" not in doc
    assert doc["properties"]["title"] == "CP 2027 Guided Health Plans : Appeal Decision"
    assert doc["properties"]["description"].startswith("This theme")
