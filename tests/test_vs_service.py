"""ValueStreamService end-to-end with fake search + LLM (Contract B)."""

from __future__ import annotations

from teg.contracts.value_stream_io import ValueStreamRequest
from teg.domain.condensed import SummaryFields
from teg.integrations.search import HistoricalHit, HistoricalValueStreamLabel, ValueStreamHit
from teg.services.value_stream_service import ValueStreamService
from teg.value_stream.config import ValueStreamConfig


class _FakeSearch:
    async def search_value_streams(self, query, *, top_k=50):
        return [ValueStreamHit("VS1", "Adjudicate Claim", score=1.4)]

    async def search_historical(self, query, *, top_k=6):
        return [
            HistoricalHit(
                "IDMT-1",
                "Claims savings",
                score=0.82,
                value_streams=[HistoricalValueStreamLabel("VS1", "Adjudicate Claim")],
            )
        ]


class _FakeLLM:
    async def complete(self, *, system, user, schema):
        return schema.model_validate(
            {"picks": [{"entityId": "VS1", "confidence": 0.9, "supportType": "implied", "reason": "claims"}]}
        )


def _request() -> ValueStreamRequest:
    return ValueStreamRequest(
        ticket_id="IDMT-9",
        summary_fields=SummaryFields(
            generated_summary="claims savings", business_problem="p", business_capability="c"
        ),
        requested_count=1,
    )


async def test_predict_end_to_end_camel_case() -> None:
    # Default (production) is evidence mode: historic is shown as a separate EVIDENCE block, not
    # merged onto candidates, so source_tickets is empty - the past tickets surface via
    # historical_tickets instead.
    service = ValueStreamService(_FakeSearch(), _FakeLLM(), model_name="m")
    response = await service.predict(_request())

    assert response.ticket_id == "IDMT-9"
    assert [r.value_stream_id for r in response.recommendations] == ["VS1"]
    rec = response.recommendations[0]
    assert rec.confidence == 90.0
    assert rec.source_tickets == []  # evidence mode does not attach historic to candidates
    assert [h.ticket_id for h in response.historical_tickets] == ["IDMT-1"]
    assert response.model == "m"

    data = response.model_dump(by_alias=True)
    assert data["recommendations"][0]["valueStreamId"] == "VS1"
    assert data["recommendations"][0]["sourceTickets"] == []


async def test_predict_merge_mode_attaches_source_tickets() -> None:
    # merge mode (experiment path) merges the historic lane onto candidates, so an implied pick
    # carries the supporting historic ticket ids.
    service = ValueStreamService(
        _FakeSearch(), _FakeLLM(), model_name="m", config=ValueStreamConfig(selection_mode="merge")
    )
    response = await service.predict(_request())

    rec = response.recommendations[0]
    assert rec.value_stream_id == "VS1"
    assert rec.source_tickets == ["IDMT-1"]  # historic-backed (VS1 hit both lanes)
