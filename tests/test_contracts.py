"""Contract smoke tests: shapes validate and serialize as camelCase JSON."""

from __future__ import annotations

from teg.contracts.condense_io import (
    CondensedTicketDTO,
    CondenseResponse,
    GenerationSignalsDTO,
    SummaryFieldsDTO,
)
from teg.contracts.theme_io import (
    ApprovedValueStreamDTO,
    CondensedContextDTO,
    ThemeGenerationRequest,
)
from teg.contracts.value_stream_io import RecommendationDTO, ValueStreamRequest


def _summary() -> SummaryFieldsDTO:
    return SummaryFieldsDTO(
        generated_summary="s",
        business_problem="p",
        business_capability="c",
        key_terms=["a"],
    )


def test_condense_response_serializes_camel_case() -> None:
    response = CondenseResponse(
        condensed=CondensedTicketDTO(
            ticket_id="IDMT-1",
            ticket_title="t",
            primary_source="idea_card",
            summary_fields=_summary(),
            generation_signals=GenerationSignalsDTO(),
            description="d",
            raw_text="r",
        ),
        model="m",
        prompt_version="v1",
    )
    data = response.model_dump(by_alias=True)
    assert data["condensed"]["summaryFields"]["generatedSummary"] == "s"
    assert data["condensed"]["generationSignals"]["marketSegments"] == []


def test_value_stream_request_round_trips_camel_case() -> None:
    payload = {
        "ticketId": "IDMT-1",
        "summaryFields": _summary().model_dump(by_alias=True),
        "requestedCount": 5,
    }
    request = ValueStreamRequest.model_validate(payload)
    assert request.ticket_id == "IDMT-1"
    assert request.requested_count == 5


def test_recommendation_enforces_confidence_and_reason_bounds() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RecommendationDTO(
            value_stream_id="VSR1",
            value_stream_name="n",
            confidence=0.1,  # below 0.30 floor
            support_type="direct",
            reason="ok",
            bucket="semantic_only",
        )


def test_theme_request_validates() -> None:
    request = ThemeGenerationRequest(
        ticket_id="IDMT-1",
        ticket_title="t",
        condensed=CondensedContextDTO(
            summary_fields=_summary(),
            generation_signals=GenerationSignalsDTO(),
        ),
        approved_value_streams=[
            ApprovedValueStreamDTO(value_stream_id="VSR1", value_stream_name="n")
        ],
    )
    assert request.approved_value_streams[0].value_stream_id == "VSR1"
