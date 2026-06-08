"""Azure AI Search implementation of SearchClient.

Two indices: the VS catalogue (hybrid text+vector, filtered to ValueStream nodes)
and the historical Engagement Requests (vector). The query is embedded via the
embeddings client. The result-mapping and the value_streams_json parsing are pure
functions (unit-tested); the SDK search calls need live creds (gated smoke test).
"""

from __future__ import annotations

import json

from teg.config.settings import Settings
from teg.integrations.embeddings import EmbeddingsClient, build_embeddings_client
from teg.integrations.search.client import (
    HistoricalHit,
    HistoricalValueStreamLabel,
    ValueStreamHit,
)

try:  # azure SDK is the optional 'search' extra
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.aio import SearchClient as _AzureSearchClient
    from azure.search.documents.models import VectorizedQuery
except Exception:  # pragma: no cover - import guarded so the module always loads
    AzureKeyCredential = None  # type: ignore[assignment]
    _AzureSearchClient = None  # type: ignore[assignment]
    VectorizedQuery = None  # type: ignore[assignment]

_VS_FILTER = "node_type eq 'ValueStream'"
_VS_SELECT = ["entity_id", "entity_name", "content"]
_HISTORICAL_SELECT = ["ticket_id", "summary_text", "value_streams_json"]


class AzureSearchClient:
    def __init__(
        self,
        *,
        vs_index_client,
        historical_index_client,
        embeddings: EmbeddingsClient,
        vector_field: str = "content_vector",
        semantic_config: str = "default",
    ) -> None:
        self._vs = vs_index_client
        self._historical = historical_index_client
        self._embeddings = embeddings
        self._vector_field = vector_field
        self._semantic_config = semantic_config

    async def search_value_streams(self, query: str, *, top_k: int = 50) -> list[ValueStreamHit]:
        vector = await self._embeddings.embed(query)
        results = await self._vs.search(
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
        results = await self._historical.search(
            search_text=None,
            vector_queries=[self._vector_query(vector, top_k)],
            select=_HISTORICAL_SELECT,
            top=top_k,
        )
        return [_to_historical_hit(doc) async for doc in results]

    def _vector_query(self, vector: list[float], top_k: int):
        return VectorizedQuery(
            vector=vector, k_nearest_neighbors=top_k, fields=self._vector_field
        )


def _to_value_stream_hit(doc) -> ValueStreamHit:
    return ValueStreamHit(
        value_stream_id=str(doc.get("entity_id") or ""),
        value_stream_name=str(doc.get("entity_name") or ""),
        value_stream_description=str(doc.get("content") or ""),
        score=float(doc.get("@search.reranker_score") or doc.get("@search.score") or 0.0),
    )


def _to_historical_hit(doc) -> HistoricalHit:
    return HistoricalHit(
        ticket_id=str(doc.get("ticket_id") or ""),
        title=str(doc.get("ticket_id") or ""),
        score=float(doc.get("@search.score") or 0.0),
        snippet=str(doc.get("summary_text") or ""),
        value_streams=_parse_value_streams_json(doc.get("value_streams_json")),
    )


def _parse_value_streams_json(raw) -> list[HistoricalValueStreamLabel]:
    if not raw:
        return []
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    labels: list[HistoricalValueStreamLabel] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        vs_id = str(item.get("vs_id") or "")
        if not vs_id:
            continue
        labels.append(
            HistoricalValueStreamLabel(
                value_stream_id=vs_id,
                value_stream_name=str(item.get("vs_name") or ""),
                support_type=str(item.get("inference_type") or ""),
                reason=str(item.get("reason") or ""),
            )
        )
    return labels


def build_search_client(settings: Settings) -> AzureSearchClient:
    if _AzureSearchClient is None:
        raise ImportError("azure-search-documents is required: install the 'search' extra")
    credential = AzureKeyCredential(settings.search_api_key)
    vs_index = _AzureSearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index_value_stream,
        credential=credential,
    )
    historical_index = _AzureSearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index_historical,
        credential=credential,
    )
    return AzureSearchClient(
        vs_index_client=vs_index,
        historical_index_client=historical_index,
        embeddings=build_embeddings_client(settings),
        vector_field=settings.search_vector_field,
        semantic_config=settings.search_semantic_config,
    )
