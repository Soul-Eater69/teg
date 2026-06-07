"""Embeddings client protocol (TDD 5.3 historical lane).

Vectorizes the query text for the vector search lane. VS retrieval depends on this
protocol; the real implementation (TEG-35) wraps the embeddings deployment.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingsClient(Protocol):
    async def embed(self, text: str) -> list[float]: ...
