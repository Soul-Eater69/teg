"""IdpLLMClient tests using a mocked HTTP transport - no live gateway calls."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from teg.integrations.llm import IdpLLMClient, LLMError


class _Out(BaseModel):
    answer: str


def _client(handler, **kwargs) -> IdpLLMClient:
    http = httpx.AsyncClient(base_url="https://gw.test", transport=httpx.MockTransport(handler))
    return IdpLLMClient(http, model="gpt-5-mini-idp", reasoning_effort="low", **kwargs)


async def test_builds_json_schema_request_and_parses_idp_choice() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["path"] = request.url.path
        return httpx.Response(200, json={"choice": {"message": {"content": '{"answer": "42"}'}}})

    out = await _client(handler).complete(system="sys", user="usr", schema=_Out)

    assert out.answer == "42"
    body = captured["body"]
    assert captured["path"] == "/chat/completions"
    assert body["model"] == "gpt-5-mini-idp"
    assert body["reasoning_effort"] == "low"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": "usr"}
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "_Out"
    assert "answer" in body["response_format"]["json_schema"]["schema"]["properties"]


async def test_parses_standard_choices_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer": "x"}'}}]})

    out = await _client(handler).complete(system="s", user="u", schema=_Out)
    assert out.answer == "x"


async def test_raises_on_error_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "boom"})

    with pytest.raises(LLMError):
        await _client(handler).complete(system="s", user="u", schema=_Out)


async def test_raises_on_unparseable_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choice": {"message": {"content": "not json"}}})

    with pytest.raises(LLMError):
        await _client(handler).complete(system="s", user="u", schema=_Out)
