"""Lock the VS retrieval protocols: fakes satisfy them; records construct."""

from __future__ import annotations

from teg.integrations.embeddings import EmbeddingsClient
from teg.integrations.search import (
    HistoricalHit,
    HistoricalValueStreamLabel,
    SearchClient,
    ValueStreamHit,
)


class _FakeSearch:
    async def search_value_streams(self, query, query_vector, *, top_k=50):
        return []

    async def search_historical(self, query_vector, *, top_k=6):
        return []


class _FakeEmbeddings:
    async def embed(self, text):
        return [0.0, 1.0]


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(_FakeSearch(), SearchClient)
    assert isinstance(_FakeEmbeddings(), EmbeddingsClient)


def test_records_construct() -> None:
    vs = ValueStreamHit(value_stream_id="VSR1", value_stream_name="Adjudicate Claim")
    assert vs.score == 0.0
    hit = HistoricalHit(
        ticket_id="IDMT-9",
        title="Claims savings",
        value_streams=[HistoricalValueStreamLabel("VSR1", "Adjudicate Claim", "implied")],
    )
    assert hit.value_streams[0].support_type == "implied"
