"""Lock the search protocol: a fake satisfies it; records construct."""

from __future__ import annotations

from teg.integrations.search import (
    HistoricalHit,
    HistoricalValueStreamLabel,
    SearchClient,
    ValueStreamHit,
)


class _FakeSearch:
    async def search_value_streams(self, query, *, top_k=50):
        return []

    async def search_historical(self, query, *, top_k=6):
        return []


def test_fake_satisfies_search_protocol() -> None:
    assert isinstance(_FakeSearch(), SearchClient)


def test_records_construct() -> None:
    vs = ValueStreamHit(value_stream_id="VSR1", value_stream_name="Adjudicate Claim")
    assert vs.score == 0.0
    hit = HistoricalHit(
        ticket_id="IDMT-9",
        title="Claims savings",
        value_streams=[HistoricalValueStreamLabel("VSR1", "Adjudicate Claim")],
    )
    assert hit.value_streams[0].value_stream_id == "VSR1"
