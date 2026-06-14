"""IDP bearer auth flow: retry once on ANY 401, including the first request of a run."""

from __future__ import annotations

import asyncio

import httpx

from teg.integrations.llm.idp_auth import IDPCustomAuth


def _auth() -> IDPCustomAuth:
    return IDPCustomAuth(
        app_id="APP", auth_url="https://idp/token", client_id="c", client_secret="s",
        user="u", password="p",
    )


def _drive(auth: IDPCustomAuth, statuses: list[int]) -> list[str]:
    """Run the auth flow against a scripted sequence of response statuses.

    Returns the Bearer token sent on each attempt (so we can assert the retry re-tokenized).
    """
    async def run() -> list[str]:
        gen = auth.async_auth_flow(httpx.Request("POST", "https://gw/chat"))
        sent: list[str] = []
        request = await gen.__anext__()
        for status in statuses:
            sent.append(request.headers["Authorization"])
            response = httpx.Response(status, request=request)
            try:
                request = await gen.asend(response)
            except StopAsyncIteration:
                break
        await gen.aclose()
        return sent

    return asyncio.run(run())


def test_first_request_401_is_retried_with_a_fresh_token(monkeypatch) -> None:
    auth = _auth()
    tokens = iter(["tok-1", "tok-2"])

    async def fake_fetch() -> str:
        return next(tokens)

    monkeypatch.setattr(auth, "_fetch_token", fake_fetch)
    # First attempt 401s on the freshly-minted token; the flow must refresh and retry.
    sent = _drive(auth, [401, 200])
    assert sent == ["Bearer tok-1", "Bearer tok-2"]  # retried with a new token, not surfaced


def test_cached_token_used_without_refetch_when_ok(monkeypatch) -> None:
    auth = _auth()
    calls = {"n": 0}

    async def fake_fetch() -> str:
        calls["n"] += 1
        return "tok"

    monkeypatch.setattr(auth, "_fetch_token", fake_fetch)
    sent = _drive(auth, [200])
    assert sent == ["Bearer tok"] and calls["n"] == 1  # one fetch, no retry on success
