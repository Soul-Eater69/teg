"""Embeddings client protocol.

Used by ingestion to vectorize documents when building the index (and available to
the search client internally if the index isn't set up for integrated vectorization).
The real implementation wraps the embeddings deployment.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingsClient(Protocol):
    async def embed(self, text: str) -> list[float]: ...
