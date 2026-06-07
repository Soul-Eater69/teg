"""VS retrieval tests with a fake search client (text-in; client owns vectorization)."""

from __future__ import annotations

from teg.domain.condensed import SummaryFields
from teg.integrations.search import HistoricalHit, ValueStreamHit
from teg.value_stream.retrieval import _build_query, retrieve


class _FakeSearch:
    def __init__(self) -> None:
        self.calls: dict = {}

    async def search_value_streams(self, query, *, top_k=50):
        self.calls["vs"] = {"query": query, "top_k": top_k}
        return [ValueStreamHit("VSR1", "Adjudicate Claim", score=1.2)]

    async def search_historical(self, query, *, top_k=6):
        self.calls["historical"] = {"query": query, "top_k": top_k}
        return [HistoricalHit("IDMT-9", "Claims savings", score=0.9)]


def _summary() -> SummaryFields:
    return SummaryFields(
        generated_summary="claims savings analysis",
        business_problem="manual claims intake",
        business_capability="automated intake",
        key_terms=["claims"],
        stakeholders=["Claims Ops"],
        systems_and_products=["ClaimsHub"],
    )


async def test_retrieve_runs_both_lanes_with_the_query_text() -> None:
    search = _FakeSearch()
    result = await retrieve(_summary(), search, vs_top_k=50, historical_top_k=6)

    assert [h.value_stream_id for h in result.value_stream_hits] == ["VSR1"]
    assert [h.ticket_id for h in result.historical_hits] == ["IDMT-9"]
    assert search.calls["vs"]["top_k"] == 50
    assert search.calls["historical"]["top_k"] == 6
    # both lanes get the same composed query text
    assert search.calls["vs"]["query"] == search.calls["historical"]["query"]
    assert "claims savings analysis" in search.calls["vs"]["query"]


def test_build_query_combines_summary_fields() -> None:
    query = _build_query(_summary())
    for token in ("claims savings analysis", "manual claims intake", "claims", "ClaimsHub"):
        assert token in query
