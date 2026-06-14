"""Evaluate generated theme descriptions - REFERENCE-FREE, against the RAW ticket text only.

Theme generation uses the raw idea card (no summary, no generation signals - consistent with the
locked VS/stage decision). We do NOT score against the GT description (each is free-form; matching
it penalises style not substance). For each ticket we generate the theme description per GT value
stream (shared body + per-VS framing) from the RAW text, then judge it ONLY against that raw text:

  faithfulness  : claims grounded in the raw ticket (no invention)  -> supported / total
  hallucination : 1 - faithfulness (the unsupported claims are listed)
  coverage      : the raw ticket's key facts reflected in the description -> covered / total

The GT file is used only to pick which value streams to generate for, never to score.

Usage (needs the LLM gateway):
  uv run python scripts/eval_description.py out/idmt/cosmos_idmt.json --sample 50 --min-vs 2
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from teg.config.settings import load_settings
from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.integrations.llm import build_llm_client
from teg.theme.description import (
    assemble_description,
    generate_description_body,
    generate_vs_framings,
)
from teg.theme.description_judges import judge_coverage, judge_faithfulness
from teg.theme.stage_catalogue import StageCatalogue

_RAW_BUDGET_CHARS = 96_000  # ~24k tokens of raw ticket text (the locked theme-gen budget)


def _load_condensed(path: str) -> dict[str, dict]:
    docs = json.loads(Path(path).read_text(encoding="utf-8"))
    return {d.get("key", ""): (d.get("properties") or {}) for d in docs if d.get("key")}


def _load_gt_vs(path: str) -> dict[str, list[tuple[str, str]]]:
    """{ticket_id: [(vs_id, vs_name)]} - the approved value streams to generate descriptions for."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, list[tuple[str, str]]] = {}
    for ticket in payload.get("tickets") or []:
        seen: dict[str, str] = {}
        for theme in ticket.get("themes") or []:
            vs_id = theme.get("value_stream_id") or ""
            if vs_id:
                seen[vs_id] = theme.get("value_stream_name") or vs_id
        if seen:
            out[ticket.get("ticket_id") or ""] = list(seen.items())
    return out


def _raw_context(props: dict, raw_budget: int) -> tuple[CondensedContext, str]:
    """Build the generation context from the RAW text only (no summary, no signals), and return it
    alongside the raw source string we judge faithfulness / coverage against."""
    raw = str(props.get("rawText") or "")[:raw_budget]
    ctx = CondensedContext(
        summary_fields=SummaryFields(generated_summary=raw, business_problem="", business_capability=""),
        generation_signals=GenerationSignals(),
    )
    return ctx, raw


async def _eval_ticket(ticket_id, props, vs_list, *, catalogue, llm, raw_budget, sem) -> list[dict]:
    async with sem:
        ctx, source = _raw_context(props, raw_budget)  # raw text = both the input and the judged source
        approved = [ApprovedValueStream(value_stream_id=v, value_stream_name=n) for v, n in vs_list]
        vs_details = {v: (catalogue.description_for(v), catalogue.value_proposition_for(v))
                      for v, _ in vs_list}
        # One shared body + one batched framing call for every VS (the production path).
        body, framings = await asyncio.gather(
            generate_description_body(condensed=ctx, llm_client=llm),
            generate_vs_framings(condensed=ctx, approved_value_streams=approved,
                                 value_stream_details=vs_details, llm_client=llm),
        )
        rows: list[dict] = []
        for vs_id, vs_name in vs_list:
            description = assemble_description(framings.get(vs_id, ""), body)
            faith, cov = await asyncio.gather(
                judge_faithfulness(description=description, source=source, llm_client=llm),
                judge_coverage(description=description, source=source, llm_client=llm),
            )
            rows.append({
                "ticket_id": ticket_id, "value_stream_id": vs_id, "value_stream_name": vs_name,
                "faithfulness": round(faith.score(), 3),
                "hallucination": round(1 - faith.score(), 3),
                "coverage": round(cov.score(), 3),
                "n_claims": len(faith.claims), "n_unsupported": len(faith.unsupported()),
                "unsupported": " | ".join(faith.unsupported()),
                "missed_facts": " | ".join(cov.missed()),
            })
        print(f"  {ticket_id}: {len(rows)} VS descriptions judged")
        return rows


async def main(args: argparse.Namespace) -> None:
    settings = load_settings()
    condensed = _load_condensed(args.condensed)
    gt_vs = _load_gt_vs(args.gt)
    catalogue = StageCatalogue.from_catalogue(load_value_stream_catalogue(args.catalogue))

    tickets = [t for t in gt_vs if t in condensed and len(gt_vs[t]) >= args.min_vs]
    if args.sample and args.sample < len(tickets):
        import random
        tickets = sorted(random.Random(args.seed).sample(tickets, args.sample))
    elif args.count:
        tickets = tickets[:args.count]
    if not tickets:
        raise SystemExit("no tickets to evaluate")
    print(f"evaluating {len(tickets)} tickets (min_vs>={args.min_vs}; raw text only)\n")

    llm = build_llm_client(settings)
    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*(
        _eval_ticket(t, condensed[t], gt_vs[t], catalogue=catalogue, llm=llm,
                     raw_budget=args.raw_budget, sem=sem)
        for t in tickets
    ))
    rows = [r for ticket in results for r in ticket]

    n = len(rows)
    avg = lambda k: sum(r[k] for r in rows) / n if n else 0.0
    print(f"\n=== description eval (reference-free, vs source) | {n} VS descriptions ===")
    print(f"  faithfulness : {avg('faithfulness'):.3f}  (claims grounded in the source)")
    print(f"  hallucination: {avg('hallucination'):.3f}  (unsupported claims)")
    print(f"  coverage     : {avg('coverage'):.3f}  (source key facts reflected)")
    print(f"  avg claims/desc={avg('n_claims'):.1f}  avg unsupported/desc={avg('n_unsupported'):.2f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    runs = out.with_suffix(".runs.json")
    prior = json.loads(runs.read_text(encoding="utf-8")) if runs.exists() else []
    prior.append({"n": n, "faithfulness": round(avg("faithfulness"), 4),
                  "hallucination": round(avg("hallucination"), 4), "coverage": round(avg("coverage"), 4)})
    runs.write_text(json.dumps(prior, indent=2), encoding="utf-8")
    print(f"\nper-description CSV -> {out}\nrun metrics -> {runs}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Reference-free description eval (faithfulness/coverage).")
    p.add_argument("condensed", help="index docs json (e.g. out/idmt/cosmos_idmt.json)")
    p.add_argument("--gt", default="out/stage_eval/stage_ground_truth.json", help="for the VS list only")
    p.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    p.add_argument("--raw-budget", type=int, default=_RAW_BUDGET_CHARS, help="raw text char budget")
    p.add_argument("--min-vs", type=int, default=1, help="min approved VS per ticket")
    p.add_argument("--sample", type=int, default=0)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--out", default="out/desc_eval/eval_description.csv")
    asyncio.run(main(p.parse_args()))
