"""Manual smoke test for the condense step against the real Jira + LLM gateway.

Prerequisites:
  1. cp .env.example .env  and fill in the gateway + IDP auth + Jira values
  2. uv sync --extra dev --extra extract   (installs markitdown)
  3. uv run python scripts/smoke_condense.py IDMT-1234
"""

from __future__ import annotations

import asyncio
import json
import sys

from teg.bootstrap import build_condense_service
from teg.contracts.condense_io import CondenseRequest


async def main(ticket_id: str) -> None:
    service = build_condense_service()
    response = await service.condense(CondenseRequest(ticket_id=ticket_id))
    condensed = response.condensed
    print(f"# source: {condensed.primary_source}  attachments: {condensed.attachments_used}")
    print(f"# model: {response.model}  prompt: {response.prompt_version}\n")
    print(json.dumps(response.model_dump(by_alias=True), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: smoke_condense.py <TICKET_ID>")
    asyncio.run(main(sys.argv[1]))
