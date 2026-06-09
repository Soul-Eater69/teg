"""Contract smoke tests: shapes validate and serialize as camelCase JSON."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teg.contracts.condense_io import CondensedTicket, CondenseRequest, CondenseResponse
from teg.contracts.theme_io import (
    ApprovedValueStream,
    CondensedContext,
    ThemeGenerationRequest,
)
from teg.contracts.value_stream_io import ValueStreamRequest
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.domain.value_stream import ValueStreamRecommendation


def _summary() -> SummaryFields:
    return SummaryFields(
        generated_summary="s",
        business_problem="p",
        business_capability="c",
        key_terms=["a"],
    )


def test_condense_response_serializes_camel_case() -> None:
    response = CondenseResponse(
        condensed=CondensedTicket(
            ticket_id="IDMT-1",
            ticket_title="t",
            primary_source="idea_card",
            summary_fields=_summary(),
            generation_signals=GenerationSignals(),
            description="d",
            raw_text="r",
        ),
        model="m",
        prompt_version="v1",
    )
    data = response.model_dump(by_alias=True)
    assert data["condensed"]["summaryFields"]["generatedSummary"] == "s"
    assert data["condensed"]["generationSignals"]["marketSegments"] == []


def test_condense_request_requires_some_input() -> None:
    with pytest.raises(ValidationError):
        CondenseRequest()
    assert CondenseRequest(ticket_id="IDMT-1").ticket_id == "IDMT-1"


def test_value_stream_request_round_trips_camel_case() -> None:
    payload = {
        "ticketId": "IDMT-1",
        "summaryFields": _summary().model_dump(by_alias=True),
        "requestedCount": 5,
    }
    request = ValueStreamRequest.model_validate(payload)
    assert request.ticket_id == "IDMT-1"
    assert request.requested_count == 5


def test_recommendation_confidence_bounded_to_0_100() -> None:
    with pytest.raises(ValidationError):
        ValueStreamRecommendation(
            value_stream_id="VSR1",
            value_stream_name="n",
            confidence=150,  # out of 0-100
            support_type="direct",
            reason="ok",
        )
    rec = ValueStreamRecommendation(
        value_stream_id="VSR1",
        value_stream_name="n",
        confidence=82,
        support_type="implied",
        reason="downstream billing impact",
    )
    assert rec.confidence == 82


def test_theme_request_validates() -> None:
    request = ThemeGenerationRequest(
        ticket_id="IDMT-1",
        ticket_title="t",
        condensed=CondensedContext(
            summary_fields=_summary(),
            generation_signals=GenerationSignals(),
        ),
        approved_value_streams=[
            ApprovedValueStream(value_stream_id="VSR1", value_stream_name="n")
        ],
    )
    assert request.approved_value_streams[0].value_stream_id == "VSR1"
