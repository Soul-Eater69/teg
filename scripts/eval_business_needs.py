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
from time import perf_counter

_GEN_LAT: list[float] = []  # per-VS generation wall-time, for the cost report
_BATCHED_LAT: list[float] = []  # batched mode: one call per TICKET (all VS together)

from teg.config.settings import load_settings
from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.integrations.llm import build_llm_client

from _judge_throttle import ThrottledClient
from teg.theme.business_needs import (
    BusinessNeedsInput,
    generate_business_needs,
    generate_business_needs_batched,
)
from teg.theme.business_needs_judges import judge_stage_usage
from teg.theme.description_judges import (
    extract_claims,
    judge_correctness,
    judge_coverage,
    judge_faithfulness,
)
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


async def _eval_ticket(ticket_id, props, gt_by_vs, *, catalogue, llm, judge, raw_budget, args, sem) -> list[dict]:
    async with sem:
        ctx, source = _raw_context(props, raw_budget)
        rows: list[dict] = []
        # value streams with usable stages for this ticket
        vs_stages = {vs_id: [s for s in catalogue.stages_for(vs_id) if s.stage_id in entry["stages"]]
                     for vs_id, entry in gt_by_vs.items()}
        vs_stages = {v: st for v, st in vs_stages.items() if st}
        if not vs_stages:
            print(f"  {ticket_id}: 0 VS"); return rows

        # produce Business Needs per VS: batched = ONE call for all VS; per_vs = N calls.
        if args.mode == "batched":
            inputs = [BusinessNeedsInput(
                value_stream=ApprovedValueStream(value_stream_id=v, value_stream_name=gt_by_vs[v]["name"]),
                value_stream_description=catalogue.description_for(v),
                value_proposition=catalogue.value_proposition_for(v),
                selected_stages=st) for v, st in vs_stages.items()]
            print(f"  {ticket_id}: generating (batched, {len(inputs)} VS, chunk={args.chunk_size})...", flush=True)
            t0 = perf_counter()
            needs_by_vs = await generate_business_needs_batched(
                condensed=ctx, inputs=inputs, llm_client=llm, chunk_size=args.chunk_size)
            dt = perf_counter() - t0
            _BATCHED_LAT.append(dt)  # wall-time per TICKET (chunks run concurrently)
            print(f"  {ticket_id}: generation done in {dt:.1f}s"
                  + ("" if args.no_judge else " - judging...") , flush=True)
        else:
            needs_by_vs = {}
            for v, st in vs_stages.items():
                t0 = perf_counter()
                needs_by_vs[v] = await generate_business_needs(
                    condensed=ctx,
                    value_stream=ApprovedValueStream(value_stream_id=v, value_stream_name=gt_by_vs[v]["name"]),
                    value_stream_description=catalogue.description_for(v),
                    value_proposition=catalogue.value_proposition_for(v),
                    selected_stages=st, llm_client=llm)
                _GEN_LAT.append(perf_counter() - t0)  # per-VS generation wall-time

        for vs_id, stages in vs_stages.items():
            needs = needs_by_vs.get(vs_id, "")
            if not needs.strip():
                continue
            if args.no_judge:  # latency-only run: generate, skip the judges
                rows.append({"ticket_id": ticket_id, "value_stream_id": vs_id, "n_stages": len(stages)})
                continue
            print(f"    {ticket_id}/{vs_id}: claim extraction...", flush=True)
            claims = await extract_claims(text=needs, llm_client=judge)  # 1. extract once
            print(f"    {ticket_id}/{vs_id}: judging {len(claims)} claims (faith/corr/cov/usage)...", flush=True)
            faith, corr, cov, usage = await asyncio.gather(             # 2/4 on claims, 3 coverage, + stage usage
                judge_faithfulness(claims=claims, source=source, llm_client=judge),
                judge_correctness(claims=claims, source=source, llm_client=judge),
                judge_coverage(description=needs, source=source, llm_client=judge),
                judge_stage_usage(business_needs=needs, stages=stages, llm_client=judge),
            )
            print(f"    {ticket_id}/{vs_id}: judged ✓", flush=True)
            rows.append({
                "ticket_id": ticket_id, "value_stream_id": vs_id, "n_stages": len(stages),
                "faithfulness": round(faith.score(), 3), "hallucination": round(1 - faith.score(), 3),
                "correctness": round(corr.score(), 3),
                "coverage": round(cov.score(), 3),
                "stage_usage": round(usage.usage(), 3), "stage_align": round(usage.alignment(), 3),
                "unsupported": " | ".join(faith.unsupported()),
                "incorrect": " | ".join(corr.incorrect()),
                "missed_facts": " | ".join(cov.missed()),
                "unused_stages": " | ".join(usage.unused()),
                "misaligned_stages": " | ".join(usage.misaligned_notes()),
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

    llm = build_llm_client(settings)  # generation = production model
    # patient retries for the rate-limited judge so a 429 window is ridden out, not surfaced.
    judge = build_llm_client(settings, model=args.judge_model, max_retries=args.judge_retries,
                             retry_max_delay=args.judge_retry_delay) if args.judge_model else llm
    judge = ThrottledClient(judge, args.judge_concurrency)  # serialise judge calls (rate-limited gpt-5)
    if args.judge_model:
        print(f"judging with: {args.judge_model} (generation: {settings.llm_model}, "
              f"judge-concurrency={args.judge_concurrency})")
    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*(
        _eval_ticket(t, condensed[t], gt[t], catalogue=catalogue, llm=llm, judge=judge,
                     raw_budget=args.raw_budget, args=args, sem=sem)
        for t in tickets
    ))
    rows = [r for ticket in results for r in ticket]
    n = len(rows)
    avg = lambda k: sum(r[k] for r in rows) / n if n else 0.0
    if not args.no_judge:
        print(f"\n=== business needs eval (reference-free, vs source) | {n} VS docs ===")
        print(f"  faithfulness : {avg('faithfulness'):.3f}  (claims grounded in the source)")
        print(f"  hallucination: {avg('hallucination'):.3f}  (unsupported claims)")
        print(f"  correctness  : {avg('correctness'):.3f}  (claims accurately stated, no distortion)")
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
                      "hallucination": round(avg("hallucination"), 4),
                      "correctness": round(avg("correctness"), 4), "coverage": round(avg("coverage"), 4),
                      "stage_usage": round(avg("stage_usage"), 4), "stage_align": round(avg("stage_align"), 4)})
        runs.write_text(json.dumps(prior, indent=2), encoding="utf-8")
    else:
        print(f"\n=== business needs (LATENCY ONLY, no judge) | {n} VS docs generated ===")
    if _GEN_LAT:
        lat = sorted(_GEN_LAT); u = llm.usage
        print(f"\ngeneration cost (per VS business-needs doc):")
        print(f"  latency  avg={sum(lat)/len(lat):.1f}s  median={lat[len(lat)//2]:.1f}s  max={lat[-1]:.1f}s")
        print(f"  tokens   {u['calls']} calls, avg {u['avg_total']:.0f}/call "
              f"({u['avg_prompt']:.0f} in / {u['avg_completion']:.0f} out), {u['total_tokens']} total")
    if _BATCHED_LAT:
        lat = sorted(_BATCHED_LAT); u = llm.usage; n = len(lat)
        print(f"\ngeneration cost (batched, ONE call per TICKET / all VS):")
        print(f"  latency  avg={sum(lat)/n:.1f}s  median={lat[n//2]:.1f}s  max={lat[-1]:.1f}s  (n={n} tickets)")
        print(f"  tokens   {u['calls']} calls, avg {u['avg_total']:.0f}/call "
              f"({u['avg_prompt']:.0f} in / {u['avg_completion']:.0f} out), {u['total_tokens']} total")
    if not args.no_judge:
        print(f"\nper-VS CSV -> {out}\nrun metrics -> {runs}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Reference-free Business Needs eval + stage usage.")
    p.add_argument("condensed", help="index docs json (e.g. out/idmt/cosmos_idmt.json)")
    p.add_argument("--gt", default="out/stage_eval/stage_ground_truth.json", help="VS + stages")
    p.add_argument("--mode", choices=["per_vs", "batched"], default="per_vs",
                   help="per_vs = one call per value stream (current); batched = chunked all-VS calls")
    p.add_argument("--chunk-size", type=int, default=2,
                   help="batched mode: value streams per call (0=all in one; small avoids huge stalling "
                        "responses - business needs are long). Default 2.")
    p.add_argument("--no-judge", action="store_true",
                   help="generate only, skip the judges - measure generation latency/tokens fast")
    p.add_argument("--judge-concurrency", type=int, default=1,
                   help="max concurrent judge calls (1 = sequential; raise if the judge tolerates it)")
    p.add_argument("--judge-retries", type=int, default=10,
                   help="judge retry budget for 429s (rate-limited gpt-5 needs more than the default 5)")
    p.add_argument("--judge-retry-delay", type=float, default=60.0,
                   help="judge max backoff seconds per 429 retry (ride out the rate window)")
    p.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    p.add_argument("--raw-budget", type=int, default=_RAW_BUDGET_CHARS)
    p.add_argument("--judge-model", default="", help="stronger model for the judges (e.g. gpt-5-idp); "
                   "empty = self-judge with the generation model (may be optimistic)")
    p.add_argument("--sample", type=int, default=0)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--out", default="out/needs_eval/eval_business_needs.csv")
    asyncio.run(main(p.parse_args()))
