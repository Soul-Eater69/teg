"""LLM client protocol.

The condense / VS / theme steps depend on this small async interface, not on a
concrete SDK. Tests inject a fake; the real implementation wraps the provider SDK
(JSON / structured-output mode, prompt caching, retries) and is configured from
:class:`teg.config.settings.Settings`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_output_tokens: int | None = None,
    ) -> str:
        """Return the model's raw text response for a system+user prompt.

        Callers that expect JSON parse the result themselves so parsing stays
        testable and the client stays a thin transport.
        """
        ...
