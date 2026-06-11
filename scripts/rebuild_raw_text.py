"""Rebuild the consolidated rawText for the eval dataset with the CURRENT condense caps.

The rawText stored in cosmos_idmt.json was built at ingestion time with whatever doc_char_budget
was then in effect. To compare raw-text vs summary under the new caps (e.g. 40k), the raw text
must reflect them. This regenerates rawText per ticket via resolve_from_ticket (download + extract
+ consolidate) using the live CondenseConfig - NO LLM call, so it's fast and cheap.

Writes a new dataset (default cosmos_idmt.rawcaps.json) with each doc's properties.rawText replaced;
everything else (summaryFields, themes GT) is untouched, so eval_vs.py can run on it directly.
Resumable + timed-out: re-run to continue.

Usage (Jira + extract deps; uv sync --extra extract):
  uv run python scripts/rebuild_raw_text.py out/idmt/cosmos_idmt.json --out out/idmt/cosmos_idmt.rawcaps.json
  uv run python -m scripts.eval_vs out/idmt/cosmos_idmt.rawcaps.json --raw-text ...   # then eval on it
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from teg.condense.config import CondenseConfig
from teg.condense.ticket_context import resolve_from_ticket
from teg.config.settings import load_settings
from teg.integrations.files import build_attachment_extractor
from teg.integrations.jira import build_jira_client


def _ticket_id(doc: dict) -> str:
    return doc.get("sourceId") or doc.get("properties", {}).get("sourceId") or doc.get("id") or ""


async def main(args) -> None:
    docs = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if not isinstance(docs, list):
        docs = [docs]
    out_path = Path(args.out)
    # Resume from a partial output if present (rawText already rebuilt for some tickets).
    prior = {}
    if out_path.exists():
        for d in json.loads(out_path.read_text(encoding="utf-8")):
            prior[_ticket_id(d)] = d.get("properties", {}).get("rawText")

    settings = load_settings()
    config = CondenseConfig(
        doc_char_budget=settings.condense_doc_char_budget,
        max_attachments=settings.condense_max_attachments,
        max_attachment_bytes=settings.condense_max_attachment_bytes,
        min_doc_chars=settings.condense_min_doc_chars,
    )
    print(f"rebuilding rawText with doc_char_budget={config.doc_char_budget}, "
          f"max_attachments={config.max_attachments}")
    jira = build_jira_client(settings)
    extractor = build_attachment_extractor()
    sem = asyncio.Semaphore(args.concurrency)
    progress = {"n": 0, "total": len(docs)}

    async def _rebuild(doc: dict) -> None:
        tid = _ticket_id(doc)
        props = doc.setdefault("properties", {})
        if tid in prior and prior[tid]:  # resume
            props["rawText"] = prior[tid]
            progress["n"] += 1
            return
        async with sem:
            try:
                ticket = await asyncio.wait_for(jira.fetch_ticket(tid), timeout=args.ticket_timeout)
                resolved = await asyncio.wait_for(
                    resolve_from_ticket(ticket, jira, extractor, config=config), timeout=args.ticket_timeout
                )
                props["rawText"] = resolved.consolidated_text
                note = f"{len(resolved.consolidated_text)} chars, src={resolved.primary_source}"
            except Exception as exc:
                note = f"ERROR {type(exc).__name__}: {exc} (kept old rawText)"
        progress["n"] += 1
        print(f"[{progress['n']}/{progress['total']}] {tid}: {note}")
        if progress["n"] % args.checkpoint_every == 0:
            out_path.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")

    await asyncio.gather(*(_rebuild(d) for d in docs))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {out_path}  ({len(docs)} docs, rawText rebuilt at the current caps)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="cosmos_idmt.json to rebuild rawText for")
    parser.add_argument("--out", default="out/idmt/cosmos_idmt.rawcaps.json")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--ticket-timeout", type=float, default=90.0)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    asyncio.run(main(parser.parse_args()))
