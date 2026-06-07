"""IDP bearer auth for the LLM gateway.

Fetches a JWT from the IDP token endpoint, caches it, injects it as
``Authorization: Bearer`` plus the ``app-id`` header, and refreshes once on a 401.
Async-only: the gateway client is an httpx.AsyncClient.
"""

from __future__ import annotations

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

    async def async_auth_flow(self, request: httpx.Request):
        fetched_now = self._token is None
        if fetched_now:
            self._token = await self._fetch_token()
        self._apply(request)

        response = yield request
        # A 401 on a cached token likely means it expired -> refresh once and retry.
        # If we just fetched the token and still got 401, the cause is not expiry
        # (bad creds / permissions), so let that 401 surface to the caller.
        if response.status_code == 401 and not fetched_now:
            self._token = await self._fetch_token()
            self._apply(request)
            yield request

    def _apply(self, request: httpx.Request) -> None:
        request.headers["Authorization"] = f"Bearer {self._token}"
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
