"""Upsert documents into the unified Azure Search index (idp_teg_data).

merge_or_upload = upsert by key (id), so re-ingesting a ticket overwrites its doc -
safe to re-run. Batched to the Azure per-request cap. Gated on the optional 'search'
extra; the batching helper is pure and unit-tested.
"""

from __future__ import annotations

from typing import Iterator

from teg.config.settings import Settings

try:  # azure SDK is the optional 'search' extra
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.aio import SearchClient as _AzureSearchClient
except Exception:  # pragma: no cover - import guarded so the module always loads
    AzureKeyCredential = None  # type: ignore[assignment]
    _AzureSearchClient = None  # type: ignore[assignment]

_BATCH_SIZE = 1000  # Azure caps a request at 1000 documents / 16 MB


def _chunk(documents: list[dict], size: int = _BATCH_SIZE) -> Iterator[list[dict]]:
    for start in range(0, len(documents), size):
        yield documents[start : start + size]


class SearchUploader:
    def __init__(self, index_client) -> None:
        self._index = index_client

    async def upload(self, documents: list[dict]) -> int:
        uploaded = 0
        for batch in _chunk(documents):
            await self._index.merge_or_upload_documents(documents=batch)
            uploaded += len(batch)
        return uploaded

    async def close(self) -> None:
        await self._index.close()


def build_search_uploader(settings: Settings) -> SearchUploader:
    if _AzureSearchClient is None:
        raise ImportError("azure-search-documents is required: install the 'search' extra")
    index_client = _AzureSearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index,
        credential=AzureKeyCredential(settings.search_api_key),
    )
    return SearchUploader(index_client)
