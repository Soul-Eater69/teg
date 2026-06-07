"""Manual smoke test for the condense step against the real Jira + LLM gateway.

Times every stage - Jira fetch, attachment download, markitdown extract, and the
two parallel LLM calls - so you can see exactly where the time goes. Then prints
the condensed package (minus the bulky description / rawText).

The condense LLM-gather wall vs the sum of the two call times tells you whether the
calls actually ran in parallel.

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

from teg.condense.condenser import condense
from teg.condense.config import CondenseConfig
from teg.condense.ticket_context import resolve_from_ticket
from teg.config.settings import load_settings
from teg.integrations.files import build_attachment_extractor
from teg.integrations.jira import build_jira_client
from teg.integrations.llm import build_llm_client
from teg.prompts.loader import load_prompt


class _TimedJira:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.downloads: list[tuple[str, float]] = []

    async def fetch_ticket(self, ticket_id):
        return await self._inner.fetch_ticket(ticket_id)

    async def download_attachment(self, attachment):
        start = perf_counter()
        try:
            return await self._inner.download_attachment(attachment)
        finally:
            self.downloads.append((attachment.filename, perf_counter() - start))


class _TimedExtractor:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.extracts: list[tuple[str, float]] = []

    def extract(self, filename, content):
        start = perf_counter()
        text = self._inner.extract(filename, content)
        self.extracts.append((filename, perf_counter() - start, len(text)))
        return text


class _TimedLLM:
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
    jira = _TimedJira(build_jira_client(settings))
    extractor = _TimedExtractor(build_attachment_extractor())
    llm = _TimedLLM(build_llm_client(settings))

    t = perf_counter()
    ticket = await jira.fetch_ticket(ticket_id)
    fetch_s = perf_counter() - t

    print("# attachments (from metadata, before any download):")
    for a in ticket.attachments:
        print(f"#   {a.filename:<44} {a.size_bytes:>13,} bytes")
    print()

    config = CondenseConfig(
        doc_char_budget=settings.condense_doc_char_budget,
        max_attachments=settings.condense_max_attachments,
        max_attachment_bytes=settings.condense_max_attachment_bytes,
        min_doc_chars=settings.condense_min_doc_chars,
    )
    t = perf_counter()
    context = await resolve_from_ticket(ticket, jira, extractor, config=config)
    resolve_s = perf_counter() - t

    t = perf_counter()
    condensed = await condense(context, llm)
    condense_s = perf_counter() - t

    total = fetch_s + resolve_s + condense_s

    print("# stage timings")
    print(f"#   jira.fetch_ticket           {fetch_s:6.2f}s")
    print(f"#   resolve (download+extract)  {resolve_s:6.2f}s")
    for name, secs in jira.downloads:
        print(f"#       download {name:<22} {secs:6.2f}s")
    for name, secs, chars in extractor.extracts:
        print(f"#       extract  {name:<22} {secs:6.2f}s  {chars:>7,} chars (markitdown)")
    print(f"#   condense LLM gather wall    {condense_s:6.2f}s")
    for name, secs in llm.calls:
        print(f"#       {name:<26} {secs:6.2f}s")
    sum_calls = sum(s for _, s in llm.calls)
    print(f"#       (sum of calls {sum_calls:.2f}s -> {'PARALLEL' if condense_s < sum_calls * 0.9 else 'SEQUENTIAL?'})")
    print(f"#   TOTAL                       {total:6.2f}s\n")

    print(f"# source: {condensed.primary_source}  attachments: {condensed.attachments_used}")
    print(f"# model: {settings.llm_model}  prompt: {load_prompt('condense/summary').version}\n")

    data = condensed.model_dump(by_alias=True)
    data.pop("description", None)
    data.pop("rawText", None)
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: smoke_condense.py <TICKET_ID>")
    asyncio.run(main(sys.argv[1]))
