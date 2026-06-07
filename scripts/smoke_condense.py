"""Manual smoke test for the condense step against the real Jira + LLM gateway.

Reports per-call LLM timings (summary + signals run in parallel) and the total
end-to-end condense time, then prints the condensed package (minus the bulky
description / rawText).

Prerequisites:
  1. cp .env.example .env  and fill in the gateway + IDP auth + Jira values
  2. uv sync --extra dev --extra extract   (installs markitdown)
  3. uv run python scripts/smoke_condense.py IDMT-1234
"""

from __future__ import annotations

import asyncio
import json
import sys
from time import perf_counter

from teg.config.settings import load_settings
from teg.contracts.condense_io import CondenseRequest
from teg.integrations.files import build_attachment_extractor
from teg.integrations.jira import build_jira_client
from teg.integrations.llm import build_llm_client
from teg.services.condense_service import CondenseService


class _TimingLLM:
    """Wraps the real LLM client to record each call's duration + schema."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[tuple[str, float]] = []

    async def complete(self, *, system, user, schema):
        start = perf_counter()
        try:
            return await self._inner.complete(system=system, user=user, schema=schema)
        finally:
            self.calls.append((schema.__name__, perf_counter() - start))


async def main(ticket_id: str) -> None:
    settings = load_settings()
    llm = _TimingLLM(build_llm_client(settings))
    service = CondenseService(
        build_jira_client(settings),
        llm,
        build_attachment_extractor(),
        model_name=settings.llm_model,
        doc_char_budget=settings.condense_doc_char_budget,
        max_attachments=settings.condense_max_attachments,
    )

    start = perf_counter()
    response = await service.condense(CondenseRequest(ticket_id=ticket_id))
    total = perf_counter() - start

    print("# timings (summary + signals run in parallel)")
    for name, secs in llm.calls:
        print(f"#   {name:<18} {secs:6.2f}s")
    print(f"#   {'TOTAL end-to-end':<18} {total:6.2f}s  (incl. Jira fetch + extract)\n")

    condensed = response.condensed
    print(f"# source: {condensed.primary_source}  attachments: {condensed.attachments_used}")
    print(f"# model: {response.model}  prompt: {response.prompt_version}\n")

    data = response.model_dump(by_alias=True)
    data["condensed"].pop("description", None)
    data["condensed"].pop("rawText", None)
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: smoke_condense.py <TICKET_ID>")
    asyncio.run(main(sys.argv[1]))
