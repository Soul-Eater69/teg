"""Evaluate L3 capability selection - per_stage vs one_call, cross-stage mislink, coverage.

L3 selection mirrors stage selection one level deeper: for each selected stage, pick the applicable
L3 capabilities from THAT stage's governed candidates. GT L3 is recorded at the THEME level (the
Theme's 'L3 Business Capability Model' field, ids CAP#####), so we aggregate the generated L3 across
the value stream's stages into a theme-level set and score it against the GT theme set.

Two modes (like stages):
  per_stage : one capability call per stage (cannot cross-link by construction)
  one_call  : one batched call for all the value stream's stages (production); also measured for
              cross-STAGE mislinking - an L3 the batched call put under the wrong stage.

Coverage = GT L3 ids that are actually in the catalogue (the recall ceiling). Raw text only.

Usage (needs the LLM gateway):
  uv run python scripts/eval_l3.py out/idmt/cosmos_idmt.json --mode both --sample 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from teg.config.settings import load_settings
from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.integrations.llm import build_llm_client
from teg.theme.capabilities import generate_capabilities, generate_capabilities_traced
from teg.theme.context import render_ticket_context
from teg.theme.l3_drop_explainer import classify_l3_drop_grounding
from teg.theme.stage_catalogue import StageCatalogue

_RAW_BUDGET = 96_000
_CAP_ID = re.compile(r"\{\s*(CAP\d+)\s*\}")  # GT L3 strings: "Name {CAP00000189}"


def _load_condensed(path: str) -> dict[str, dict]:
    docs = json.loads(Path(path).read_text(encoding="utf-8"))
    return {d.get("key", ""): (d.get("properties") or {}) for d in docs if d.get("key")}


def _load_gt(path: str) -> dict[str, dict[str, dict]]:
    """{ticket_id: {vs_id: {"name", "stages": set[stage_id], "l3": set[CAP id]}}}."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict[str, dict]] = {}
    for ticket in payload.get("tickets") or []:
        by_vs: dict[str, dict] = {}
        for theme in ticket.get("themes") or []:
            vs_id = theme.get("value_stream_id") or ""
            if not vs_id:
                continue
            stages = {s.get("stage_id") for s in theme.get("stages") or [] if s.get("stage_id")}
            l3 = {m for cap in (theme.get("l3_capabilities") or []) for m in _CAP_ID.findall(str(cap))}
            if stages and l3:
                e = by_vs.setdefault(vs_id, {"name": theme.get("value_stream_name") or "",
                                            "stages": set(), "l3": set()})
                e["stages"] |= stages
                e["l3"] |= l3
        if by_vs:
            out[ticket.get("ticket_id") or ""] = by_vs
    return out


def _ctx(props: dict) -> CondensedContext:
    return CondensedContext(
        summary_fields=SummaryFields(generated_summary=str(props.get("rawText") or "")[:_RAW_BUDGET],
                                     business_problem="", business_capability=""),
        generation_signals=GenerationSignals())


def _div(a, b):
    return a / b if b else 0.0


def _prf(pred: set, gt: set) -> tuple[int, int, int]:
    tp = len(pred & gt)
    return tp, len(pred) - tp, len(gt) - tp


async def _eval_ticket(ticket_id, props, gt_by_vs, *, catalogue, llm, args, sem) -> dict:
    async with sem:
        ctx = _ctx(props)
        res = {"ticket_id": ticket_id, "per_vs_pairs": [], "one_call_pairs": [], "mislink": [],
               "coverage": [], "drops": []}
        for vs_id, entry in gt_by_vs.items():
            stages = [s for s in catalogue.stages_for(vs_id) if s.stage_id in entry["stages"]
                      and s.capabilities]
            if not stages:
                continue
            cat_l3 = {c.capability_id for s in stages for c in s.capabilities}
            gt_l3 = entry["l3"]
            res["coverage"].append((len(gt_l3 & cat_l3), len(gt_l3)))
            # Score against ANSWERABLE GT L3 only: the GT theme L3 reachable from the GT stages'
            # candidate lists. GT L3 that map to stages not in the selection are unpredictable, so
            # scoring them as FN tanks recall - this is the real, fair recall (like pruning
            # uncatalogued stages). Coverage above is reported separately as the ceiling.
            gt_scored = gt_l3 & cat_l3
            if not gt_scored:
                continue
            vs = ApprovedValueStream(value_stream_id=vs_id, value_stream_name=entry["name"])
            desc = catalogue.description_for(vs_id)

            if args.mode in ("per_stage", "both"):
                per = await asyncio.gather(*(generate_capabilities(
                    condensed=ctx, value_stream=vs, value_stream_description=desc,
                    selected_stages=[s], llm_client=llm) for s in stages))
                pred = {c.capability_id for l3, _ in per for sc in l3 for c in sc.capabilities}
                res["per_vs_pairs"].append(_prf(pred, gt_scored))
            if args.mode in ("one_call", "both"):
                l3, _l2, raw = await generate_capabilities_traced(
                    condensed=ctx, value_stream=vs, value_stream_description=desc,
                    selected_stages=stages, llm_client=llm)
                pred = {c.capability_id for sc in l3 for c in sc.capabilities}
                res["one_call_pairs"].append(_prf(pred, gt_scored))
                res["mislink"].append(_mislink(raw, stages))
                # Drop diagnosis: per stage, why was an answerable GT L3 (in this stage's candidate
                # list) not picked? Every candidate was in the prompt -> 'saw it, didn't pick it'.
                if args.ground_drops:
                    picked_by_stage = {sc.stage_id: {c.capability_id for c in sc.capabilities}
                                       for sc in l3}
                    ticket_ctx = render_ticket_context(ctx)
                    for s in stages:
                        stage_gt = {c.capability_id for c in s.capabilities} & gt_l3
                        dropped = sorted(stage_gt - picked_by_stage.get(s.stage_id, set()))
                        if not dropped:
                            continue
                        try:
                            g = await classify_l3_drop_grounding(
                                ticket_context=ticket_ctx, stage_name=s.stage_name,
                                candidates=s.capabilities, dropped_ids=dropped, llm_client=llm)
                            for cid in dropped:
                                res["drops"].append(g[cid].grounding if cid in g else "other")
                        except Exception as exc:
                            print(f"    ground-drops failed {vs_id}/{s.stage_id}: {exc}")
        print(f"  {ticket_id}: {len(res['coverage'])} VS scored")
        return res


def _mislink(raw_picks: dict[str, list[str]], stages) -> dict:
    """An L3 the batched call put under a stage that doesn't own it = a cross-stage mislink."""
    owner = {c.capability_id: s.stage_id for s in stages for c in s.capabilities}
    total = foreign = 0
    for stage_id, picks in raw_picks.items():
        for cid in picks:
            total += 1
            if owner.get(cid) not in (None, stage_id):
                foreign += 1
    return {"total": total, "foreign": foreign}


def _agg(pairs: list[tuple[int, int, int]]) -> dict:
    tp = sum(p[0] for p in pairs); fp = sum(p[1] for p in pairs); fn = sum(p[2] for p in pairs)
    p = _div(tp, tp + fp); r = _div(tp, tp + fn)
    return {"n": len(pairs), "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(_div(2 * p * r, p + r), 4)}


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
        raise SystemExit("no tickets with L3 GT overlap the docs")
    print(f"evaluating {len(tickets)} tickets (raw text only)\n")

    llm = build_llm_client(settings)
    sem = asyncio.Semaphore(args.concurrency)
    rows = await asyncio.gather(*(
        _eval_ticket(t, condensed[t], gt[t], catalogue=catalogue, llm=llm, args=args, sem=sem)
        for t in tickets))

    cov = [c for r in rows for c in r["coverage"]]
    in_cat = sum(a for a, _ in cov); gt_tot = sum(b for _, b in cov)
    print(f"\n=== L3 capability eval | {len(cov)} VS ===")
    print(f"  GT-in-catalogue coverage: {in_cat}/{gt_tot} ({_div(in_cat, gt_tot):.0%}) "
          f"- of theme GT L3 reachable from the GT stages; P/R/F1 below score the answerable ones only")
    for mode, key in (("per_stage", "per_vs_pairs"), ("one_call", "one_call_pairs")):
        pairs = [p for r in rows for p in r[key]]
        if not pairs:
            continue
        m = _agg(pairs)
        print(f"  [{mode:9}] P={m['precision']}  R={m['recall']}  F1={m['f1']}  (n={m['n']})")
    ml = [m for r in rows for m in r["mislink"]]
    if ml:
        tot = sum(m["total"] for m in ml); fr = sum(m["foreign"] for m in ml)
        print(f"  one_call mislink (L3 under wrong stage): {fr}/{tot} ({_div(fr, tot):.1%})")
    drops = [d for r in rows for d in r["drops"]]
    if drops:
        from collections import Counter
        c = Counter(drops); n = len(drops)
        fixable = c.get("context_present_but_dropped", 0)
        noise = c.get("no_context_for_capability", 0)
        print(f"\n  [drop grounding] {n} answerable GT L3 dropped:")
        for code, cnt in c.most_common():
            print(f"    {code:30} {cnt:4}  ({_div(cnt, n):.0%})")
        print(f"    -> {_div(fixable, n):.0%} FIXABLE (card supports it, dropped anyway); "
              f"{_div(noise, n):.0%} convention/label-noise (no card evidence)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    runs = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    runs.append({"n_vs": len(cov), "coverage": round(_div(in_cat, gt_tot), 4),
                 "per_stage": _agg([p for r in rows for p in r["per_vs_pairs"]]) if any(r["per_vs_pairs"] for r in rows) else None,
                 "one_call": _agg([p for r in rows for p in r["one_call_pairs"]]) if any(r["one_call_pairs"] for r in rows) else None})
    out.write_text(json.dumps(runs, indent=2), encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="L3 capability selection eval (per_stage vs one_call).")
    p.add_argument("condensed")
    p.add_argument("--gt", default="out/stage_eval/stage_ground_truth.json")
    p.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    p.add_argument("--mode", choices=["per_stage", "one_call", "both"], default="both")
    p.add_argument("--ground-drops", action="store_true",
                   help="classify each dropped answerable GT L3 (one_call): card-supported-but-dropped "
                        "(fixable) vs no-card-evidence (convention/label noise) vs weak")
    p.add_argument("--sample", type=int, default=0)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--out", default="out/l3_eval/eval_l3.runs.json")
    asyncio.run(main(p.parse_args()))
