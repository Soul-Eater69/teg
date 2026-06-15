"""Predict Value Streams directly from an idea card (no Jira ticket id needed).

Takes idea-card text (a file or stdin), condenses it into summaryFields + rawText, then runs the
production Value Stream selection (evidence mode: raw text + the 50 governed VS + the 6 similar
historical tickets as precedent) and prints the recommended Value Streams.

This is the runtime path of Figure 2 starting from the idea card itself instead of a ticket id - the
Jira fetch / attachment extraction steps are skipped because you already hand it the idea-card text.

Usage:
  uv run python scripts/predict_value_streams.py idea_card.txt
  uv run python scripts/predict_value_streams.py idea_card.txt --count 6 --title "Real-time CPQ"
  cat idea_card.txt | uv run python scripts/predict_value_streams.py -
  uv run python scripts/predict_value_streams.py idea_card.txt --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from teg.bootstrap import build_value_stream_service
from teg.condense.condenser import condense
from teg.condense.models import ResolvedContext
from teg.config.settings import load_settings
from teg.contracts.value_stream_io import ValueStreamRequest
from teg.integrations.files.document_extractor import build_attachment_extractor
from teg.integrations.llm import build_llm_client

_RAW_BUDGET_CHARS = 96_000  # ~24k tokens, the ingest budget (idea card is already small)
_TEXT_EXTS = {".txt", ".md", ".text"}


def _read_idea_card(path: str) -> str:
    """Read an idea card from text (.txt/.md) or extract it from .pdf/.pptx/.docx; '-' = stdin text."""
    if path == "-":
        text = sys.stdin.read()
    else:
        p = Path(path)
        if p.suffix.lower() in _TEXT_EXTS:
            text = p.read_text(encoding="utf-8", errors="ignore")
        else:  # .pdf / .pptx / .docx -> extract (same path as ingestion attachments)
            text = build_attachment_extractor().extract(p.name, p.read_bytes())
    text = text.strip()
    if not text:
        raise SystemExit("idea card is empty / no text extracted "
                         "(image-only PDF, or legacy .ppt/.doc — convert to .pptx/.docx)")
    return text[:_RAW_BUDGET_CHARS]


async def main(args: argparse.Namespace) -> None:
    idea_card = _read_idea_card(args.idea_card)
    settings = load_settings()

    # 1. Condense the idea card -> summaryFields (retrieval) + rawText (selection prompt).
    context = ResolvedContext(
        ticket_id=args.id,
        ticket_title=args.title,
        description="",
        primary_source="idea_card",
        attachments_used=[],
        consolidated_text=idea_card,
    )
    llm = build_llm_client(settings)
    try:
        condensed = await condense(context, llm)
    finally:
        await llm.aclose()  # close the condense LLM session

    # 2. Run production Value Stream selection (evidence mode is the config default).
    #    summary_fields = the embedding/retrieval query; prompt_text = raw idea card the LLM reads.
    service = build_value_stream_service(settings)
    request = ValueStreamRequest(
        ticket_id=args.id,
        summary_fields=condensed.summary_fields,
        prompt_text=condensed.raw_text,
        requested_count=args.count,
        custom_instruction=args.instruction,
    )
    try:
        response = await service.predict(request)
    finally:
        await service.aclose()  # close the search + selection-LLM sessions

    if args.json:
        print(json.dumps(response.model_dump(by_alias=True), indent=2, ensure_ascii=False))
        return

    recs = response.recommendations
    print(f"\nValue Streams for {args.id!r}  ({len(recs)} of {args.count} requested, model={response.model})\n")
    print(f"{'#':>2}  {'value stream':40} {'conf':>4}  {'support':8}  reason")
    print("-" * 110)
    for i, r in enumerate(recs, 1):
        vs = f"{r.value_stream_name} ({r.value_stream_id})"
        srcs = f"  ← {', '.join(r.source_tickets)}" if getattr(r, "source_tickets", None) else ""
        print(f"{i:>2}  {vs[:40]:40} {r.confidence:>4}  {r.support_type:8}  {r.reason[:60]}{srcs}")
    if response.historical_tickets:
        print(f"\nsimilar past tickets used as precedent: "
              f"{', '.join(h.ticket_id for h in response.historical_tickets)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Predict Value Streams from an idea card.")
    p.add_argument("idea_card", help="path to idea-card text file, or '-' for stdin")
    p.add_argument("--count", type=int, default=10, help="how many Value Streams to return (default 10)")
    p.add_argument("--id", default="IDEA-CARD", help="label for the run (default IDEA-CARD)")
    p.add_argument("--title", default="", help="optional idea-card title")
    p.add_argument("--instruction", default=None,
                   help="optional custom instruction (count-only, e.g. 'give me 6')")
    p.add_argument("--json", action="store_true", help="print the full response as JSON")
    asyncio.run(main(p.parse_args()))
