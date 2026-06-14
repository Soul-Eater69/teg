"""Extract generation signals from the stored rawText, into a sidecar for the stage eval.

Stage selection reads businessSolutionObjectives (a generation signal), but the index docs store
only summary fields - so stage selection has been running blind. The signals come from one LLM
call over the consolidated text, and that text IS the stored properties.rawText. So we re-run ONLY
the signals pass on the stored rawText (no Jira, no attachment extraction, no summary re-condense)
and write {ticket key: generationSignals} to a sidecar the eval loads.

Resumable: re-run to fill in any tickets missing from the sidecar.

The sidecar is a SEPARATE file (out/stage_eval/signals.json) - cosmos_idmt.json is never modified,
so the ingest artifacts stay clean for other experiments. The eval overlays the signals at runtime.

Usage (needs the LLM gateway):
  uv run python scripts/extract_signals.py out/idmt/cosmos_idmt.json
  uv run python scripts/extract_signals.py out/idmt/cosmos_idmt.json --keys IDMT-10429 IDMT-10428
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from teg.config.settings import load_settings
from teg.domain.condensed import GenerationSignals
from teg.integrations.llm import build_llm_client
from teg.prompts.loader import load_prompt


def _load_docs(path: str) -> dict[str, str]:
    """{ticket key: rawText} from the index docs."""
    docs = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for d in docs:
        key = d.get("key") or d.get("ticketId") or ""
        raw = (d.get("properties") or {}).get("rawText") or ""
        if key and raw.strip():
            out[key] = raw
    return out


async def main(args: argparse.Namespace) -> None:
    settings = load_settings()
    raw_by_key = _load_docs(args.dataset)
    if args.keys:
        raw_by_key = {k: v for k, v in raw_by_key.items() if k in set(args.keys)}

    out_path = Path(args.out)
    done: dict[str, dict] = {}
    if out_path.exists() and not args.fresh:
        done = json.loads(out_path.read_text(encoding="utf-8"))
    todo = [k for k in raw_by_key if k not in done]
    print(f"{len(raw_by_key)} tickets; {len(done)} already have signals, {len(todo)} to extract")
    if not todo:
        return

    llm = build_llm_client(settings)
    prompt = load_prompt("condense/signals")
    sem = asyncio.Semaphore(args.concurrency)
    progress = {"n": 0}

    async def _one(key: str) -> tuple[str, dict | None]:
        async with sem:
            system, user = prompt.render(ticket_id=key, consolidated_text=raw_by_key[key])
            try:
                signals = await llm.complete(system=system, user=user, schema=GenerationSignals)
            except Exception as exc:
                print(f"  ERROR {key}: {type(exc).__name__}: {exc}")
                return key, None
            progress["n"] += 1
            n_obj = len(signals.business_solution_objectives)
            print(f"  [{progress['n']}/{len(todo)}] {key}: {n_obj} solution objectives")
            return key, signals.model_dump(by_alias=True)

    results = await asyncio.gather(*(_one(k) for k in todo))
    for key, sig in results:
        if sig is not None:
            done[key] = sig

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
    have_obj = sum(1 for s in done.values() if s.get("businessSolutionObjectives"))
    print(f"\n-> {out_path}  ({len(done)} tickets, {have_obj} with >=1 solution objective)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Extract generation signals from stored rawText.")
    p.add_argument("dataset", help="index docs json (e.g. out/idmt/cosmos_idmt.json)")
    p.add_argument("--out", default="out/stage_eval/signals.json")  # separate from the ingest docs
    p.add_argument("--keys", nargs="*", help="limit to these ticket keys")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--fresh", action="store_true", help="ignore an existing sidecar, re-extract all")
    asyncio.run(main(p.parse_args()))
