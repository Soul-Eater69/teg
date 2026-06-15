"""Evaluate generated Business Needs - REFERENCE-FREE (vs raw source) + stage usage.

Business Needs are generated per approved value stream for its SELECTED stages (here: the GT
stages), structured one 'Value Stage:' block per stage, from the RAW idea card only (no summary, no
signals - the locked theme-gen decision). We judge each value stream's Business Needs against:

  faithfulness  : claims grounded in the raw ticket (no invention)  -> supported / total
  hallucination : 1 - faithfulness (the unsupported claims listed)
  coverage      : the raw ticket's key facts reflected               -> covered / total
  stage_usage   : selected stages addressed in the output            -> addressed / total
  stage_align   : addressed stages whose needs fit the stage scope   -> aligned / addressed

The GT file supplies the value streams + their (catalogued) stages; it is never scored as text.

Usage (needs the LLM gateway):
  uv run python scripts/eval_business_needs.py out/idmt/cosmos_idmt.json --sample 50
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
from teg.theme.business_needs import generate_business_needs
from teg.theme.business_needs_judges import judge_stage_usage
from teg.theme.description_judges import judge_coverage, judge_faithfulness
from teg.theme.stage_catalogue import StageCatalogue

_RAW_BUDGET_CHARS = 96_000  # ~24k tokens (locked theme-gen budget)


def _load_condensed(path: str) -> dict[str, dict]:
    docs = json.loads(Path(path).read_text(encoding="utf-8"))
    return {d.get("key", ""): (d.get("properties") or {}) for d in docs if d.get("key")}


def _load_gt(path: str) -> dict[str, dict[str, dict]]:
    """{ticket_id: {vs_id: {"name", "stages": set[stage_id]}}} - catalogued GT stages per VS."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict[str, dict]] = {}
    for ticket in payload.get("tickets") or []:
        by_vs: dict[str, dict] = {}
        for theme in ticket.get("themes") or []:
            vs_id = theme.get("value_stream_id") or ""
            stages = {s.get("stage_id") for s in theme.get("stages") or [] if s.get("stage_id")}
            if vs_id and stages:
                e = by_vs.setdefault(vs_id, {"name": theme.get("value_stream_name") or "", "stages": set()})
                e["stages"] |= stages
        if by_vs:
            out[ticket.get("ticket_id") or ""] = by_vs
    return out


def _raw_context(props: dict, raw_budget: int) -> tuple[CondensedContext, str]:
    raw = str(props.get("rawText") or "")[:raw_budget]
    ctx = CondensedContext(
        summary_fields=SummaryFields(generated_summary=raw, business_problem="", business_capability=""),
        generation_signals=GenerationSignals())
    return ctx, raw


async def _eval_ticket(ticket_id, props, gt_by_vs, *, catalogue, llm, raw_budget, sem) -> list[dict]:
    async with sem:
        ctx, source = _raw_context(props, raw_budget)
        rows: list[dict] = []
        for vs_id, entry in gt_by_vs.items():
            stages = [s for s in catalogue.stages_for(vs_id) if s.stage_id in entry["stages"]]
            if not stages:
                continue
            needs = await generate_business_needs(
                condensed=ctx,
                value_stream=ApprovedValueStream(value_stream_id=vs_id, value_stream_name=entry["name"]),
                value_stream_description=catalogue.description_for(vs_id),
                value_proposition=catalogue.value_proposition_for(vs_id),
                selected_stages=stages, llm_client=llm)
            if not needs.strip():
                continue
            faith, cov, usage = await asyncio.gather(
                judge_faithfulness(description=needs, source=source, llm_client=llm),
                judge_coverage(description=needs, source=source, llm_client=llm),
                judge_stage_usage(business_needs=needs, stages=stages, llm_client=llm),
            )
            rows.append({
                "ticket_id": ticket_id, "value_stream_id": vs_id, "n_stages": len(stages),
                "faithfulness": round(faith.score(), 3), "hallucination": round(1 - faith.score(), 3),
                "coverage": round(cov.score(), 3),
                "stage_usage": round(usage.usage(), 3), "stage_align": round(usage.alignment(), 3),
                "unsupported": " | ".join(faith.unsupported()),
                "unused_stages": " | ".join(usage.unused()),
                "misaligned_stages": " | ".join(usage.misaligned()),
            })
        print(f"  {ticket_id}: {len(rows)} VS business-needs judged")
        return rows


async def main(args: argparse.Namespace) -> None:
    settings = load_settings()
    condensed = _load_condensed(args.condensed)
    gt = _load_gt(args.gt)
    catalogue = StageCatalogue.from_catalogue(load_value_stream_catalogue(args.catalogue))

    tickets = [t for t in gt if t in condensed]
    if args.sample and args.sample < len(tickets):
        import random
        tickets = sorted(random.Random(args.seed).sample(tickets, args.sample))
    elif args.count:
        tickets = tickets[:args.count]
    if not tickets:
        raise SystemExit("no tickets to evaluate")
    print(f"evaluating {len(tickets)} tickets (raw text only)\n")

    llm = build_llm_client(settings)
    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*(
        _eval_ticket(t, condensed[t], gt[t], catalogue=catalogue, llm=llm,
                     raw_budget=args.raw_budget, sem=sem)
        for t in tickets
    ))
    rows = [r for ticket in results for r in ticket]
    n = len(rows)
    avg = lambda k: sum(r[k] for r in rows) / n if n else 0.0
    print(f"\n=== business needs eval (reference-free, vs source) | {n} VS docs ===")
    print(f"  faithfulness : {avg('faithfulness'):.3f}  (claims grounded in the source)")
    print(f"  hallucination: {avg('hallucination'):.3f}  (unsupported claims)")
    print(f"  coverage     : {avg('coverage'):.3f}  (source key facts reflected)")
    print(f"  stage usage  : {avg('stage_usage'):.3f}  (selected stages addressed)")
    print(f"  stage align  : {avg('stage_align'):.3f}  (addressed stages in-scope)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    runs = out.with_suffix(".runs.json")
    prior = json.loads(runs.read_text(encoding="utf-8")) if runs.exists() else []
    prior.append({"n": n, "faithfulness": round(avg("faithfulness"), 4),
                  "hallucination": round(avg("hallucination"), 4), "coverage": round(avg("coverage"), 4),
                  "stage_usage": round(avg("stage_usage"), 4), "stage_align": round(avg("stage_align"), 4)})
    runs.write_text(json.dumps(prior, indent=2), encoding="utf-8")
    print(f"\nper-VS CSV -> {out}\nrun metrics -> {runs}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Reference-free Business Needs eval + stage usage.")
    p.add_argument("condensed", help="index docs json (e.g. out/idmt/cosmos_idmt.json)")
    p.add_argument("--gt", default="out/stage_eval/stage_ground_truth.json", help="VS + stages")
    p.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    p.add_argument("--raw-budget", type=int, default=_RAW_BUDGET_CHARS)
    p.add_argument("--sample", type=int, default=0)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--out", default="out/needs_eval/eval_business_needs.csv")
    asyncio.run(main(p.parse_args()))
