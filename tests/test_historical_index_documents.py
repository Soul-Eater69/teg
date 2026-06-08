"""Historical IDMT search-index document builder (Generator C)."""

from __future__ import annotations

from teg.domain.condensed import CondensedTicket, GenerationSignals, SummaryFields
from teg.ingestion.documents.historical_index_documents import (
    build_historical_content,
    build_historical_index_document,
)
from teg.ingestion.extraction.jira_records import ExtractedEngagementRequest
from teg.ingestion.ground_truth.theme_ground_truth import ThemeGroundTruth


def _condensed() -> CondensedTicket:
    return CondensedTicket(
        ticket_id="IDMT-19761",
        ticket_title="t",
        primary_source="idea_card",
        summary_fields=SummaryFields(
            generated_summary="Automate appeals handling",
            business_problem="Manual appeals are slow",
            business_capability="Faster resolution",
            key_terms=["appeals"],
        ),
        generation_signals=GenerationSignals(),
        description="d",
        raw_text="r",
    )


def _er() -> ExtractedEngagementRequest:
    return ExtractedEngagementRequest(stable_id="3364549", key="IDMT-19761", title="t")


def _gt() -> list[ThemeGroundTruth]:
    return [
        ThemeGroundTruth(
            theme_stable_id="3966046",
            group_key="GROUP-23618",
            value_stream_id="VSR00074590",
            value_stream_name="Resolve Appeal",
            support_type="direct",
            reason="centers on appeals",
            evidence="processed appeal",
        )
    ]


def test_content_matches_query_builder() -> None:
    # The historical content must be built the same way as the prediction query.
    from teg.value_stream.retrieval import build_retrieval_text

    content = build_historical_content(_condensed())
    assert content == build_retrieval_text(_condensed().summary_fields)
    assert "Automate appeals handling" in content and "Manual appeals are slow" in content


def test_historical_index_document_shape() -> None:
    doc = build_historical_index_document(
        er=_er(), condensed=_condensed(), theme_gt=_gt(), content_vector=[0.1, 0.2]
    )
    assert doc["id"] == "3364549"
    assert doc["sourceId"] == "IDMT-19761"
    assert doc["entityType"] == "EngagementRequest"
    assert doc["content_vector"] == [0.1, 0.2]
    props = doc["properties"]
    assert props["summary"] == "Automate appeals handling"
    label = props["valueStreams"][0]
    assert label["valueStreamId"] == "VSR00074590"
    assert label["supportType"] == "direct"
    assert label["evidence"] == "processed appeal"
    assert "content" in doc and "valueStages" not in props  # historical, not catalogue


def test_no_vector_when_not_embedded() -> None:
    doc = build_historical_index_document(er=_er(), condensed=_condensed(), theme_gt=[])
    assert doc["content_vector"] is None
    assert doc["properties"]["valueStreams"] == []
