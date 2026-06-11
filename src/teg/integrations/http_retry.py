"""Shared async POST-with-retry for the IDP gateway (LLM + embeddings).

Retries rate-limit (429), server (5xx) and transient network errors with exponential backoff +
jitter, honoring a Retry-After header when present. Other 4xx fail fast (a bad request won't fix
itself). One implementation so the LLM and embeddings clients behave identically under load.
"""

from __future__ import annotations

import asyncio
import random

import httpx


def retry_after_seconds(response: httpx.Response) -> float | None:
    """The Retry-After header in seconds, if present in integer-seconds form."""
    value = response.headers.get("retry-after") or response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None  # HTTP-date form not handled; caller falls back to computed backoff


def _backoff(attempt: int, base: float, cap: float) -> float:
    delay = min(base * (2 ** attempt), cap)
    return delay * (0.5 + random.random() / 2)  # jitter in [0.5x, 1x]


async def post_with_retry(
    http: httpx.AsyncClient,
    path: str,
    json: dict,
    *,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> httpx.Response:
    """POST json to path, retrying 429/5xx/transient-network with backoff. Returns the response
    (status already checked OK); raises on non-retryable 4xx or after exhausting retries."""
    for attempt in range(max_retries + 1):
        try:
            response = await http.post(path, json=json)
        except (httpx.TransportError, httpx.TimeoutException) as exc:  # transient network
            if attempt >= max_retries:
                raise
            await asyncio.sleep(_backoff(attempt, base_delay, max_delay))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt >= max_retries:
                response.raise_for_status()  # out of retries -> surface the real error
            delay = retry_after_seconds(response) or _backoff(attempt, base_delay, max_delay)
            await asyncio.sleep(delay)
            continue
        response.raise_for_status()  # other 4xx -> fail fast
        return response
    raise RuntimeError("unreachable retry state")  # pragma: no cover
