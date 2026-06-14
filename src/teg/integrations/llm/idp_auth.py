"""IDP bearer auth for the LLM gateway.

Fetches a JWT from the IDP token endpoint, caches it, injects it as
``Authorization: Bearer`` plus the ``app-id`` header, and refreshes once on a 401.
Async-only: the gateway client is an httpx.AsyncClient.

A freshly-minted token can be transiently rejected by the gateway (activation /
propagation delay) - so we retry once on ANY 401, including the very first request of a
run. A lock coalesces concurrent first-fetches so high concurrency doesn't stampede the
token endpoint (and only one coroutine refreshes per rejected token).
"""

from __future__ import annotations

import asyncio

import httpx


class IDPCustomAuth(httpx.Auth):
    def __init__(
        self,
        *,
        app_id: str,
        auth_url: str,
        client_id: str,
        client_secret: str,
        user: str,
        password: str,
        verify_ssl: bool = False,
    ) -> None:
        self._app_id = app_id
        self._auth_url = auth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._user = user
        self._password = password
        self._verify_ssl = verify_ssl
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def async_auth_flow(self, request: httpx.Request):
        token = await self._ensure_token(stale=None)
        self._apply(request, token)

        response = yield request
        # Any 401 -> the token was rejected (expired, OR a freshly-minted token not yet active
        # on the gateway - the first request of a run hits this). Refresh once and retry. A
        # second 401 then surfaces to the caller (genuinely bad creds / permissions).
        if response.status_code == 401:
            token = await self._ensure_token(stale=token)
            self._apply(request, token)
            yield request

    async def _ensure_token(self, *, stale: str | None) -> str:
        """Return a usable token, fetching one under the lock if missing or matching ``stale``.

        Passing the token that just 401'd as ``stale`` means only the first coroutine to see
        that rejection re-fetches; the rest reuse the new token instead of stampeding.
        """
        async with self._lock:
            if self._token is None or self._token == stale:
                self._token = await self._fetch_token()
            return self._token

    def _apply(self, request: httpx.Request, token: str) -> None:
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["app-id"] = str(self._app_id)

    async def _fetch_token(self) -> str:
        headers = {
            "Accept": "*/*",
            "ClientId": self._client_id,
            "ClientSecret": self._client_secret,
            "scope": "profile openid roles permissions",
        }
        body = {"username": self._user, "password": self._password}
        async with httpx.AsyncClient(verify=self._verify_ssl) as client:
            response = await client.post(self._auth_url, headers=headers, json=body)
        response.raise_for_status()
        token = response.json().get("jwt_token")
        if not token:
            raise RuntimeError("IDP token response missing jwt_token")
        return str(token)
