"""IdpEmbeddingsClient tests using a mocked HTTP transport - no live gateway."""

from __future__ import annotations

import json

import httpx
import pytest

from teg.integrations.embeddings import EmbeddingsClient, EmbeddingsError, IdpEmbeddingsClient


def _client(handler) -> IdpEmbeddingsClient:
    http = httpx.AsyncClient(base_url="https://gw.test", transport=httpx.MockTransport(handler))
    return IdpEmbeddingsClient(http, model="text-embedding-3-large", dimensions=3072)


async def test_embed_posts_payload_and_parses_vector() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [{"vector": [0.1, 0.2, 0.3]}]})

    vector = await _client(handler).embed("risk adjustment")

    assert vector == [0.1, 0.2, 0.3]
    assert captured["path"] == "/api/v1/embeddings"
    body = captured["body"]
    assert body["input"] == ["risk adjustment"]
    assert body["model"] == "text-embedding-3-large"
    assert body["dimensions"] == 3072


async def test_embed_many_returns_all_vectors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [{"vector": [1.0]}, {"vector": [2.0]}]})

    assert await _client(handler).embed_many(["a", "b"]) == [[1.0], [2.0]]


async def test_unexpected_response_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"oops": 1})

    with pytest.raises(EmbeddingsError):
        await _client(handler).embed("x")


def test_fake_satisfies_protocol() -> None:
    class _Fake:
        async def embed(self, text):
            return [0.0]

        async def embed_many(self, texts):
            return [[0.0]]

    assert isinstance(_Fake(), EmbeddingsClient)
