"""VS retrieval lanes (TDD 5.3 / ticket B3).

Builds a retrieval query from the condensed summary, embeds it once, and runs the
two lanes in parallel: the VS-catalogue lane (hybrid) and the historical-ER lane
(vector, top-6, shown to the SME). Returns the raw hits; bucketing/ranking is the
merger's job.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from teg.domain.condensed import SummaryFields
from teg.integrations.embeddings import EmbeddingsClient
from teg.integrations.search import HistoricalHit, SearchClient, ValueStreamHit

# Winning retrieval knobs: RAG_SEMANTIC_FETCH_K / RAG_HISTORICAL_TICKET_FETCH_K.
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
    embeddings: EmbeddingsClient,
    *,
    vs_top_k: int = _VS_TOP_K,
    historical_top_k: int = _HISTORICAL_TOP_K,
) -> RetrievalResult:
    query = _build_query(summary)
    query_vector = await embeddings.embed(query)
    vs_hits, historical_hits = await asyncio.gather(
        search_client.search_value_streams(query, query_vector, top_k=vs_top_k),
        search_client.search_historical(query_vector, top_k=historical_top_k),
    )
    return RetrievalResult(
        value_stream_hits=list(vs_hits),
        historical_hits=list(historical_hits),
    )
