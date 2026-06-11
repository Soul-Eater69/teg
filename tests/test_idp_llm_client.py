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
    assert captured["path"] == "/api/v1/chatcompletions"
    assert body["model"] == "gpt-5-mini-idp"
    assert body["reasoning_effort"] == "low"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": "usr"}
    assert body["response_format"]["type"] == "json_schema"
    js = body["response_format"]["json_schema"]
    assert js["name"] == "_Out"
    assert js["strict"] is True  # strict structured output
    schema = js["schema"]
    assert "answer" in schema["properties"]
    assert schema["required"] == ["answer"]  # strict: every property required
    assert schema["additionalProperties"] is False


async def test_parses_standard_choices_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer": "x"}'}}]})

    out = await _client(handler).complete(system="s", user="u", schema=_Out)
    assert out.answer == "x"


def test_strict_schema_makes_nested_defaults_strict_compatible() -> None:
    from pydantic import Field

    from teg.integrations.llm.idp_gateway import _strict_schema

    class _Item(BaseModel):
        id: str
        note: str = ""  # defaulted -> must become required, no default key

    class _Wrap(BaseModel):
        items: list[_Item] = Field(default_factory=list)

    schema = _strict_schema(_Wrap)
    assert schema["required"] == ["items"]
    assert schema["additionalProperties"] is False
    item = schema["$defs"]["_Item"]
    assert set(item["required"]) == {"id", "note"}  # defaulted field forced required
    assert item["additionalProperties"] is False
    assert "default" not in item["properties"]["note"]  # default key stripped


async def test_unwraps_single_key_wrapped_output() -> None:
    # Non-strict json_schema: the model sometimes wraps the payload under one key.
    def handler(request: httpx.Request) -> httpx.Response:
        wrapped = '{"_Out": {"answer": "42"}}'
        return httpx.Response(200, json={"choice": {"message": {"content": wrapped}}})

    out = await _client(handler).complete(system="s", user="u", schema=_Out)
    assert out.answer == "42"  # unwrapped one level


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


async def test_retries_on_429_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:  # fail twice, then succeed
            return httpx.Response(429, headers={"retry-after": "0"}, json={"error": "rate"})
        return httpx.Response(200, json={"choice": {"message": {"content": '{"answer": "ok"}'}}})

    client = _client(handler, max_retries=5, retry_base_delay=0.0)
    out = await client.complete(system="s", user="u", schema=_Out)
    assert out.answer == "ok"
    assert calls["n"] == 3  # two retries then success


async def test_gives_up_after_max_retries() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "down"})

    client = _client(handler, max_retries=2, retry_base_delay=0.0)
    with pytest.raises(Exception):
        await client.complete(system="s", user="u", schema=_Out)
    assert calls["n"] == 3  # initial + 2 retries


async def test_does_not_retry_on_400() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    client = _client(handler, max_retries=5, retry_base_delay=0.0)
    with pytest.raises(Exception):
        await client.complete(system="s", user="u", schema=_Out)
    assert calls["n"] == 1  # 4xx fails fast, no retry
