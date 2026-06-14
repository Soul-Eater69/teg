"""IDP bearer auth flow: retry once on ANY 401, including the first request of a run."""

from __future__ import annotations

import asyncio

import httpx

from teg.integrations.llm import idp_auth
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


def test_fetch_token_retries_transient_401_then_succeeds(monkeypatch) -> None:
    # The dev STS sometimes 401s the first token POST (server_error / secret store), then recovers.
    monkeypatch.setattr(idp_auth, "_TOKEN_BACKOFF_SECONDS", 0.0)  # no real sleep in the test
    statuses = iter([401, 503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        return httpx.Response(status, json={"jwt_token": "tok"} if status == 200 else {"error": "server_error"})

    auth = IDPCustomAuth(app_id="APP", auth_url="https://idp/token", client_id="c",
                         client_secret="s", user="u", password="p",
                         transport=httpx.MockTransport(handler))
    assert asyncio.run(auth._fetch_token()) == "tok"  # rode through the 401 + 503


def test_fetch_token_surfaces_a_real_4xx(monkeypatch) -> None:
    monkeypatch.setattr(idp_auth, "_TOKEN_BACKOFF_SECONDS", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})  # not in the retry set

    auth = IDPCustomAuth(app_id="APP", auth_url="https://idp/token", client_id="c",
                         client_secret="s", user="u", password="p",
                         transport=httpx.MockTransport(handler))
    try:
        asyncio.run(auth._fetch_token())
        assert False, "expected a 403 to surface"
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 403
