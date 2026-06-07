"""Lock the embeddings protocol: a fake satisfies it."""

from __future__ import annotations

from teg.integrations.embeddings import EmbeddingsClient


class _FakeEmbeddings:
    async def embed(self, text):
        return [0.0, 1.0]


def test_fake_satisfies_embeddings_protocol() -> None:
    assert isinstance(_FakeEmbeddings(), EmbeddingsClient)
