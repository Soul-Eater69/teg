"""VS retrieval lanes.

Builds a retrieval query from the condensed summary and runs the two lanes in
parallel: the VS-catalogue lane and the historical-ER lane (top-6, shown to the SME).
The search client owns query vectorization. Returns the raw hits; bucketing and
ranking are the merger's job.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from teg.domain.condensed import SummaryFields
from teg.integrations.search import HistoricalHit, SearchClient, ValueStreamHit

# Winning retrieval knobs.
_VS_TOP_K = 50
_HISTORICAL_TOP_K = 6


@dataclass
class RetrievalResult:
    value_stream_hits: list[ValueStreamHit] = field(default_factory=list)
    historical_hits: list[HistoricalHit] = field(default_factory=list)


def _build_query(summary: SummaryFields) -> str:
    parts = [summary.generated_summary, summary.business_problem, summary.business_capability]
    parts += summary.key_terms + summary.stakeholders + summary.systems_and_products
    return "\n".join(part for part in parts if part and part.strip())


async def retrieve(
    summary: SummaryFields,
    search_client: SearchClient,
    *,
    vs_top_k: int = _VS_TOP_K,
    historical_top_k: int = _HISTORICAL_TOP_K,
) -> RetrievalResult:
    query = _build_query(summary)
    vs_hits, historical_hits = await asyncio.gather(
        search_client.search_value_streams(query, top_k=vs_top_k),
        search_client.search_historical(query, top_k=historical_top_k),
    )
    return RetrievalResult(
        value_stream_hits=list(vs_hits),
        historical_hits=list(historical_hits),
    )
