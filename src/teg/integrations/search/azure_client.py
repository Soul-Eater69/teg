"""Azure AI Search implementation of SearchClient.

One unified index (idp_teg_data) holds both doc types our ingestion produces; the
``entityType`` field is the lane discriminator: 'ValueStream' for the catalogue lane
(hybrid text+vector+semantic), 'EngagementRequest' for the historical lane (pure
vector). The query is embedded via the embeddings client. Result mapping reads our
generated nested ``properties`` shape; the pure mappers are unit-tested, the SDK search
calls need live creds (gated smoke test).
"""

from __future__ import annotations

from teg.config.settings import Settings
from teg.integrations.embeddings import EmbeddingsClient, build_embeddings_client
from teg.integrations.search.client import (
    HistoricalHit,
    HistoricalValueStreamLabel,
    ValueStreamHit,
)
from teg.integrations.search.credential import build_search_credential

try:  # azure SDK is the optional 'search' extra
    from azure.search.documents.aio import SearchClient as _AzureSearchClient
    from azure.search.documents.models import VectorizedQuery
except Exception:  # pragma: no cover - import guarded so the module always loads
    _AzureSearchClient = None  # type: ignore[assignment]
    VectorizedQuery = None  # type: ignore[assignment]

_VS_FILTER = "entityType eq 'ValueStream'"
_HISTORICAL_FILTER = "entityType eq 'EngagementRequest'"
_RERANKER_SCALE = 4.0  # Azure semantic reranker scores are 0-4
_VS_SELECT = [
    "id",
    "properties/valueStreamId",
    "properties/valueStreamName",
    "properties/valueStreamDescription",
    "properties/category",
    "properties/trigger",
    "properties/valueProposition",
]
_HISTORICAL_SELECT = ["id", "sourceId", "properties/summary", "properties/valueStreams"]


class AzureSearchClient:
    def __init__(
        self,
        *,
        index_client,
        embeddings: EmbeddingsClient,
        vector_field: str = "content_vector",
        semantic_config: str = "teg-semantic",
    ) -> None:
        self._index = index_client
        self._embeddings = embeddings
        self._vector_field = vector_field
        self._semantic_config = semantic_config

    async def search_value_streams(self, query: str, *, top_k: int = 50) -> list[ValueStreamHit]:
        vector = await self._embeddings.embed(query)
        results = await self._index.search(
            search_text=query,
            vector_queries=[self._vector_query(vector, top_k)],
            filter=_VS_FILTER,
            select=_VS_SELECT,
            top=top_k,
            query_type="semantic",
            semantic_configuration_name=self._semantic_config,
        )
        return [_to_value_stream_hit(doc) async for doc in results]

    async def search_historical(self, query: str, *, top_k: int = 6) -> list[HistoricalHit]:
        vector = await self._embeddings.embed(query)
        results = await self._index.search(
            search_text=query,  # hybrid (BM25 + vector) + semantic rerank, same as the VS lane
            vector_queries=[self._vector_query(vector, top_k)],
            filter=_HISTORICAL_FILTER,
            select=_HISTORICAL_SELECT,
            top=top_k,
            query_type="semantic",
            semantic_configuration_name=self._semantic_config,
        )
        return [_to_historical_hit(doc) async for doc in results]

    def _vector_query(self, vector: list[float], top_k: int):
        return VectorizedQuery(
            vector=vector, k_nearest_neighbors=top_k, fields=self._vector_field
        )


def _props(doc) -> dict:
    props = doc.get("properties")
    return props if isinstance(props, dict) else {}


def _to_value_stream_hit(doc) -> ValueStreamHit:
    props = _props(doc)
    return ValueStreamHit(
        value_stream_id=str(props.get("valueStreamId") or ""),
        value_stream_name=str(props.get("valueStreamName") or ""),
        value_stream_description=str(props.get("valueStreamDescription") or ""),
        category=str(props.get("category") or ""),
        trigger=str(props.get("trigger") or ""),
        value_proposition=str(props.get("valueProposition") or ""),
        score=float(doc.get("@search.reranker_score") or doc.get("@search.score") or 0.0),
    )


def _to_historical_hit(doc) -> HistoricalHit:
    props = _props(doc)
    ticket_id = str(doc.get("sourceId") or doc.get("id") or "")
    return HistoricalHit(
        ticket_id=ticket_id,
        title=ticket_id,
        score=_historical_score(doc),
        snippet=str(props.get("summary") or ""),
        value_streams=_parse_value_streams(props.get("valueStreams")),
    )


def _historical_score(doc) -> float:
    """Historical relevance on a 0-1 scale for the merger's support bands.

    The lane is hybrid+semantic, so prefer the semantic reranker score - but normalize it
    from its 0-4 range down to 0-1, the scale the merger's support-weight bands and historic
    gates are tuned to. Falls back to the raw search score (already ~0-1) if no reranker.
    """
    reranker = doc.get("@search.reranker_score")
    if reranker is not None:
        return min(1.0, float(reranker) / _RERANKER_SCALE)
    return float(doc.get("@search.score") or 0.0)


def _parse_value_streams(raw) -> list[HistoricalValueStreamLabel]:
    """Map the native valueStreams collection (our generated shape) to labels."""
    if not isinstance(raw, list):
        return []
    labels: list[HistoricalValueStreamLabel] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        vs_id = str(item.get("valueStreamId") or "")
        if not vs_id:
            continue
        labels.append(
            HistoricalValueStreamLabel(
                value_stream_id=vs_id,
                value_stream_name=str(item.get("valueStreamName") or ""),
                support_type=str(item.get("supportType") or ""),
                reason=str(item.get("reason") or ""),
                evidence=str(item.get("evidence") or ""),
            )
        )
    return labels


def build_search_client(settings: Settings) -> AzureSearchClient:
    if _AzureSearchClient is None:
        raise ImportError("azure-search-documents is required: install the 'search' extra")
    index_client = _AzureSearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index,
        credential=build_search_credential(settings),
    )
    return AzureSearchClient(
        index_client=index_client,
        embeddings=build_embeddings_client(settings),
        vector_field=settings.search_vector_field,
        semantic_config=settings.search_semantic_config,
    )
