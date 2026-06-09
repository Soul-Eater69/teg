"""Manual smoke test for Value Stream prediction against the live indices.

Two modes:
  - raw summary text:  uv run python -m scripts.smoke_value_stream "claims savings ..." [count]
  - real IDMT ticket:  uv run python -m scripts.smoke_value_stream --ticket IDMT-19761 [count]
      (fetches + condenses the ticket first, then predicts off its summaryFields)

Prerequisites:
  cp .env.example .env  (search + LLM/IDP creds; Jira creds too for --ticket)
  uv sync --extra dev --extra search --extra extract
"""

from __future__ import annotations

import argparse
import asyncio
from time import perf_counter

from teg.bootstrap import build_condense_service, build_value_stream_service
from teg.contracts.condense_io import CondenseRequest
from teg.contracts.value_stream_io import ValueStreamRequest
from teg.domain.condensed import SummaryFields


async def main(*, ticket: str | None, summary_text: str | None, count: int) -> None:
    if ticket:
        print(f"# condensing {ticket} ...")
        t0 = perf_counter()
        condensed = (await build_condense_service().condense(CondenseRequest(ticket_id=ticket))).condensed
        print(f"# condensed in {perf_counter() - t0:.2f}s")
        print(f"#   summary: {condensed.summary_fields.generated_summary[:120]}")
        summary_fields = condensed.summary_fields
        ticket_id = ticket
    else:
        summary_fields = SummaryFields(
            generated_summary=summary_text or "", business_problem="", business_capability=""
        )
        ticket_id = "SMOKE"

    request = ValueStreamRequest(
        ticket_id=ticket_id, summary_fields=summary_fields, requested_count=count
    )
    start = perf_counter()
    response = await build_value_stream_service().predict(request)
    print(f"\n# {len(response.recommendations)} recommendations in {perf_counter() - start:.2f}s\n")
    for r in response.recommendations:
        print(
            f"  {r.confidence:5.1f}  {r.support_type:8} "
            f"{r.value_stream_name}  ({r.value_stream_id})  tickets={r.source_tickets}"
        )
    print("\n# historical tickets (for SME selection):")
    for h in response.historical_tickets:
        print(f"  {h.score:.3f}  {h.ticket_id}  {h.snippet[:80]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", nargs="?", help="raw summary text (omit when using --ticket)")
    parser.add_argument("--ticket", help="IDMT ticket id; condense it first, then predict")
    parser.add_argument("count", nargs="?", type=int, default=10)
    args = parser.parse_args()
    if not args.ticket and not args.summary:
        raise SystemExit('usage: smoke_value_stream.py "<summary>" [count]  |  --ticket IDMT-#### [count]')
    asyncio.run(main(ticket=args.ticket, summary_text=args.summary, count=args.count))
