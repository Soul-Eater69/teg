"""Throttle an LLM client's calls through a semaphore - so rate-limited judges (e.g. gpt-5) don't
get a burst of concurrent calls that exhausts the retry budget with 429s. Wraps complete()."""
from __future__ import annotations

import asyncio


class ThrottledClient:
    def __init__(self, client, max_concurrent: int) -> None:
        self._client = client
        self._sem = asyncio.Semaphore(max(1, max_concurrent))

    async def complete(self, **kwargs):
        async with self._sem:
            return await self._client.complete(**kwargs)

    @property
    def usage(self) -> dict:
        return self._client.usage

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()
