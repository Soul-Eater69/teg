"""IDP bearer auth for the LLM gateway (ported from the POC).

Fetches a JWT from the IDP token endpoint, caches it with a short TTL, injects it
as ``Authorization: Bearer`` plus the ``app-id`` header on every request, and
refreshes once on a 401. An ``SSO_TOKEN`` env var overrides the fetch when present.
"""

from __future__ import annotations

import logging
import os
import threading
import time

import httpx
import requests

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 300
OPENAI_COMPAT_API_KEY = "idp-auth-managed"  # dummy key; real auth is the bearer token


def _fetch_idp_token(
    *, auth_url: str, client_id: str, client_secret: str, user: str, password: str
) -> str:
    """POST credentials to the IDP token endpoint and return the JWT."""
    headers = {
        "Accept": "*/*",
        "ClientSecret": client_secret,
        "Content-Type": "application/json",
        "ClientId": client_id,
        "scope": "profile openid roles permissions",
    }
    response = requests.post(
        auth_url, headers=headers, json={"username": user, "password": password}, verify=False
    )
    response.raise_for_status()
    body = response.json()
    token = body.get("jwt_token") or body.get("access_token") or body.get("token")
    if not token:
        raise RuntimeError(f"IDP response had no token. Keys: {list(body.keys())}")
    logger.info("IDP token acquired from %s", auth_url)
    return str(token)


class IDPCustomAuth(httpx.Auth):
    requires_request_body = True

    def __init__(
        self,
        *,
        app_id: str,
        auth_url: str,
        client_id: str,
        client_secret: str,
        user: str,
        password: str,
    ) -> None:
        self._app_id = app_id
        self._auth_url = auth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._user = user
        self._password = password
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def _sso_override(self) -> str | None:
        token = (os.environ.get("SSO_TOKEN") or "").strip()
        if not token or token.lower() in {"none", "null", "undefined"} or token.count(".") != 2:
            return None
        return token

    def _ensure_token(self) -> str | None:
        sso = self._sso_override()
        if sso:
            return sso
        if self._token and time.time() < self._expires_at - 30:
            return self._token
        with self._lock:
            if self._token and time.time() < self._expires_at - 30:
                return self._token
            try:
                self._token = _fetch_idp_token(
                    auth_url=self._auth_url,
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                    user=self._user,
                    password=self._password,
                )
                self._expires_at = time.time() + _DEFAULT_TTL
            except Exception as exc:  # noqa: BLE001 - proceed unauthenticated; gateway returns 401
                logger.error("IDP token fetch failed: %s", exc)
                self._token, self._expires_at = None, 0.0
            return self._token

    def _apply(self, request: httpx.Request, token: str | None) -> None:
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
        request.headers["Content-Type"] = "application/json"
        request.headers["app-id"] = str(self._app_id)

    def auth_flow(self, request: httpx.Request):
        self._apply(request, self._ensure_token())
        response = yield request
        if response.status_code == 401 and not self._sso_override():
            self._token = None
            self._apply(request, self._ensure_token())
            yield request

    async def async_auth_flow(self, request: httpx.Request):
        self._apply(request, self._ensure_token())
        response = yield request
        if response.status_code == 401 and not self._sso_override():
            self._token = None
            self._apply(request, self._ensure_token())
            yield request
