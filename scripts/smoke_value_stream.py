"""Manual smoke test for Value Stream prediction against the live indices.

Prerequisites:
  1. cp .env.example .env  and fill in search + LLM/IDP + embeddings values
  2. uv sync --extra dev --extra search
  3. uv run python scripts/smoke_value_stream.py "<ticket summary text>" [count]
"""

from __future__ import annotations

import asyncio
import sys
from time import perf_counter

from teg.bootstrap import build_value_stream_service
from teg.contracts.value_stream_io import ValueStreamRequest
from teg.domain.condensed import SummaryFields


async def main(summary_text: str, count: int) -> None:
    service = build_value_stream_service()
    request = ValueStreamRequest(
        ticket_id="SMOKE",
        summary_fields=SummaryFields(
            generated_summary=summary_text, business_problem="", business_capability=""
        ),
        requested_count=count,
    )

    start = perf_counter()
    response = await service.predict(request)
    elapsed = perf_counter() - start

    print(f"# {len(response.recommendations)} recommendations in {elapsed:.2f}s\n")
    for r in response.recommendations:
        print(
            f"  {r.confidence:5.1f}  {r.support_type:8} "
            f"{r.value_stream_name}  ({r.value_stream_id})  tickets={r.source_tickets}"
        )
    print("\n# historical tickets (for SME selection):")
    for h in response.historical_tickets:
        print(f"  {h.score:.3f}  {h.ticket_id}  {h.snippet[:80]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit('usage: smoke_value_stream.py "<summary text>" [count]')
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 10))
