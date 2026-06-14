"""Evaluate stage selection against the Jira stage ground truth.

Feeds each ticket's GROUND-TRUTH value streams (isolating stage quality from VS-prediction
error) plus each VS's governed candidate stages, predicts stages, and scores the picks
against stage_ground_truth.json. Two selection modes are compared:

  per_vs   - one LLM call per value stream (cannot cross-link by construction)
  one_call - one batched call for every VS at once (today's production path); also measured
             for cross-VS mislinking - stages the batched call put under the wrong VS

Two input representations are compared via --input: the stored summary fields, or the raw
ticket text (budgeted). NOTE: the persisted docs store only summary fields, so generation
signals (businessSolutionObjectives) are empty here - stage selection runs without them.

Every metric is logged to the runs file (append-only) so comparisons are never partial.

Usage (needs the LLM gateway; offline-tested logic):
  uv run python scripts/eval_stages.py out/idmt/cosmos_idmt.json --mode both --input summary
  uv run python scripts/eval_stages.py out/idmt/cosmos_idmt.json --mode one_call --input both --count 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from teg.config.settings import load_settings
from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.integrations.llm import build_llm_client
from teg.theme.stage_catalogue import StageCatalogue
from teg.theme.stage_selection import (
    StageSelectionInput,
    select_stages,
    select_stages_for_all_traced,
)

_RAW_BUDGET_CHARS = 24_000  # ~6k tokens of raw ticket text for the --input raw axis


# ---------------------------------------------------------------------------- #
# Pure scoring (offline-tested)
# ---------------------------------------------------------------------------- #


def score_pair(predicted: set[str], gt: set[str]) -> tuple[int, int, int]:
    """(true positives, false positives, false negatives) for one (ticket, VS) pair."""
    tp = len(predicted & gt)
    return tp, len(predicted) - tp, len(gt) - tp


def mislink_counts(
    raw_picks: dict[str, list[str]], stages_by_vs: dict[str, set[str]]
) -> dict[str, int]:
    """Cross-VS mislinking in a batched pick set.

    ``raw_picks`` = {vs_id: [stage_id picked under that VS]}; ``stages_by_vs`` = each VS's
    governed catalogue stage ids. A pick foreign to its own VS is a mislink; if it belongs
    to ANOTHER evaluated VS it is a true cross-VS link, otherwise an invalid/hallucinated id.
    """
    total = foreign = cross_vs = invalid = 0
    for vs_id, picks in raw_picks.items():
        own = stages_by_vs.get(vs_id, set())
        others = set().union(*(s for k, s in stages_by_vs.items() if k != vs_id)) if stages_by_vs else set()
        for stage_id in picks:
            total += 1
            if stage_id in own:
                continue
            foreign += 1
            cross_vs += 1 if stage_id in others else 0
            invalid += 0 if stage_id in others else 1
    return {"total_picks": total, "foreign": foreign, "cross_vs": cross_vs, "invalid": invalid}


def _div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _aggregate(pairs: list[dict], mislink: list[dict[str, int]] | None) -> dict:
    """Micro + macro P/R/F1 and fetch stats over all (ticket, VS) pairs."""
    tp = sum(p["tp"] for p in pairs)
    fp = sum(p["fp"] for p in pairs)
    fn = sum(p["fn"] for p in pairs)
    micro_p, micro_r = _div(tp, tp + fp), _div(tp, tp + fn)
    macro_p = _div(sum(_div(p["tp"], p["tp"] + p["fp"]) for p in pairs), len(pairs))
    macro_r = _div(sum(_div(p["tp"], p["tp"] + p["fn"]) for p in pairs), len(pairs))
    out = {
        "n_pairs": len(pairs),
        "micro": {"precision": round(micro_p, 4), "recall": round(micro_r, 4),
                  "f1": round(_div(2 * micro_p * micro_r, micro_p + micro_r), 4)},
        "macro": {"precision": round(macro_p, 4), "recall": round(macro_r, 4),
                  "f1": round(_div(2 * macro_p * macro_r, macro_p + macro_r), 4)},
        "fallback_rate": round(_div(sum(p["fallback"] for p in pairs), len(pairs)), 4),
        "avg_predicted": round(_div(sum(p["n_pred"] for p in pairs), len(pairs)), 3),
        "avg_gt": round(_div(sum(p["n_gt"] for p in pairs), len(pairs)), 3),
    }
    if mislink is not None:
        agg = {k: sum(m[k] for m in mislink) for k in ("total_picks", "foreign", "cross_vs", "invalid")}
        agg["mislink_rate"] = round(_div(agg["foreign"], agg["total_picks"]), 4)
        agg["cross_vs_rate"] = round(_div(agg["cross_vs"], agg["total_picks"]), 4)
        out["mislink"] = agg
    return out


# ---------------------------------------------------------------------------- #
# Loading
# ---------------------------------------------------------------------------- #


def _load_condensed(path: str) -> dict[str, dict]:
    docs = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(docs, dict):
        docs = docs.get("documents") or docs.get("tickets") or []
    return {d.get("key", ""): (d.get("properties") or {}) for d in docs if d.get("key")}


def _load_gt(path: str) -> dict[str, dict[str, dict]]:
    """{ticket_id: {vs_id: {"name": str, "stages": set[stage_id]}}} - resolved stages only."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict[str, dict]] = {}
    for ticket in payload.get("tickets") or []:
        by_vs: dict[str, dict] = {}
        for theme in ticket.get("themes") or []:
            vs_id = theme.get("value_stream_id") or ""
            stages = {s.get("stage_id") for s in theme.get("stages") or [] if s.get("stage_id")}
            if vs_id and stages:
                entry = by_vs.setdefault(vs_id, {"name": theme.get("value_stream_name") or "", "stages": set()})
                entry["stages"] |= stages
        if by_vs:
            out[ticket.get("ticket_id") or ""] = by_vs
    return out


def _condensed_context(props: dict, *, raw: bool, raw_budget: int) -> CondensedContext:
    if raw:
        fields = SummaryFields(
            generated_summary=str(props.get("rawText") or "")[:raw_budget],
            business_problem="", business_capability="",
        )
    else:
        fields = SummaryFields(
            generated_summary=str(props.get("businessSummary") or ""),
            business_problem=str(props.get("businessProblem") or ""),
            business_capability=str(props.get("businessCapability") or ""),
            key_terms=list(props.get("keyTerms") or []),
            stakeholders=list(props.get("stakeholders") or []),
            systems_and_products=list(props.get("systemsAndProducts") or []),
        )
    return CondensedContext(summary_fields=fields, generation_signals=GenerationSignals())


# ---------------------------------------------------------------------------- #
# Per-ticket prediction
# ---------------------------------------------------------------------------- #


def _pair_row(predicted: list, gt: set[str], candidate_ids: set[str]) -> dict:
    pred = {s.stage_id for s in predicted}
    tp, fp, fn = score_pair(pred, gt)
    # Fallback = the resolver returned the whole lifecycle (empty/invalid LLM pick).
    fallback = 1 if pred == candidate_ids and pred != gt else 0
    return {"tp": tp, "fp": fp, "fn": fn, "fallback": fallback, "n_pred": len(pred), "n_gt": len(gt)}


async def _eval_ticket(
    ticket_id: str, props: dict, gt_by_vs: dict[str, dict], *,
    catalogue: StageCatalogue, llm, args, sem,
) -> dict:
    async with sem:
        ctx = _condensed_context(props, raw=(args.input == "raw"), raw_budget=args.raw_budget)
        inputs: list[StageSelectionInput] = []
        gt_ids: dict[str, set[str]] = {}
        cand_ids: dict[str, set[str]] = {}
        coverage: list[tuple[int, int]] = []  # (GT stages in the catalogue, GT stages total) per VS
        skipped_vs = 0  # VS whose id has no catalogue entry at all
        for vs_id, entry in gt_by_vs.items():
            stages = catalogue.stages_for(vs_id)
            if not stages:  # no catalogue entry -> can't predict/score this VS
                skipped_vs += 1
                continue
            cand = {s.stage_id for s in stages}
            coverage.append((len(entry["stages"] & cand), len(entry["stages"])))
            inputs.append(StageSelectionInput(
                value_stream=ApprovedValueStream(value_stream_id=vs_id, value_stream_name=entry["name"]),
                value_stream_description=catalogue.description_for(vs_id),
                value_proposition=catalogue.value_proposition_for(vs_id),
                stages=stages,
            ))
            gt_ids[vs_id] = entry["stages"]
            cand_ids[vs_id] = cand
        base = {"ticket_id": ticket_id, "per_vs": [], "one_call": [], "mislink": [],
                "coverage": coverage, "skipped_vs": skipped_vs}
        if not inputs:
            return base

        result: dict = base
        if args.mode in ("per_vs", "both"):
            per = await asyncio.gather(*(
                select_stages(condensed=ctx, value_stream=i.value_stream,
                              value_stream_description=i.value_stream_description,
                              value_proposition=i.value_proposition, stages=i.stages, llm_client=llm)
                for i in inputs
            ))
            result["per_vs"] = [
                _pair_row(per[idx], gt_ids[i.value_stream.value_stream_id],
                          cand_ids[i.value_stream.value_stream_id])
                for idx, i in enumerate(inputs)
            ]
        if args.mode in ("one_call", "both"):
            resolved, raw_picks = await select_stages_for_all_traced(
                condensed=ctx, inputs=inputs, llm_client=llm)
            result["one_call"] = [
                _pair_row(resolved.get(vs_id, []), gt_ids[vs_id], cand_ids[vs_id]) for vs_id in gt_ids
            ]
            result["mislink"] = [mislink_counts(raw_picks, cand_ids)]
        print(f"  {ticket_id}: {len(inputs)} VS scored")
        return result


async def main(args: argparse.Namespace) -> None:
    settings = load_settings()
    condensed = _load_condensed(args.condensed)
    gt = _load_gt(args.gt)
    catalogue = StageCatalogue.from_catalogue(load_value_stream_catalogue(args.catalogue))

    tickets = [t for t in gt if t in condensed]
    if args.count:
        tickets = tickets[:args.count]
    if not tickets:
        raise SystemExit("no tickets overlap between condensed docs and stage GT")

    inputs_axis = ["summary", "raw"] if args.input == "both" else [args.input]
    llm = build_llm_client(settings)
    sem = asyncio.Semaphore(args.concurrency)

    results_by_run: list[dict] = []
    for input_repr in inputs_axis:
        run_args = argparse.Namespace(**{**vars(args), "input": input_repr})
        print(f"\n=== input={input_repr} | mode={args.mode} | {len(tickets)} tickets ===")
        rows = await asyncio.gather(*(
            _eval_ticket(t, condensed[t], gt[t], catalogue=catalogue, llm=llm, args=run_args, sem=sem)
            for t in tickets
        ))
        # Coverage = the recall ceiling: are the GT stage ids even in the catalogue the LLM picks
        # from? Low coverage = a stage-id mismatch between the GT field and the catalogue, not a
        # model failure - so we print it BEFORE the metrics.
        cov = [c for r in rows for c in r.get("coverage", [])]
        in_cat = sum(a for a, _ in cov)
        gt_total = sum(b for _, b in cov)
        skipped = sum(r.get("skipped_vs", 0) for r in rows)
        print(f"  GT-in-catalogue coverage: {in_cat}/{gt_total} stage ids "
              f"({_div(in_cat, gt_total):.0%}) across {len(cov)} scored VS; "
              f"{skipped} VS skipped (id not in catalogue)")
        if gt_total and _div(in_cat, gt_total) < 0.5:
            print("  [!] LOW coverage - GT stage ids mostly absent from the catalogue: likely an "
                  "id-space mismatch (the eval can't credit a GT stage the LLM can't pick).")
        for mode in (("per_vs", "one_call") if args.mode == "both" else (args.mode,)):
            pairs = [p for r in rows for p in r[mode]]
            if not pairs:
                continue
            mislink = [m for r in rows for m in r["mislink"]] if mode == "one_call" else None
            metrics = _aggregate(pairs, mislink)
            results_by_run.append({"input": input_repr, "mode": mode, "n_tickets": len(tickets), **metrics})
            _print_metrics(input_repr, mode, metrics)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    runs = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    runs.append({
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "config": {"mode": args.mode, "input": args.input, "raw_budget": args.raw_budget,
                   "condensed": args.condensed, "gt": args.gt, "n_tickets": len(tickets)},
        "results": results_by_run,
    })
    out.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> appended run to {out}")


def _print_metrics(input_repr: str, mode: str, m: dict) -> None:
    print(f"\n[{input_repr} / {mode}] pairs={m['n_pairs']}")
    print(f"  micro  P={m['micro']['precision']}  R={m['micro']['recall']}  F1={m['micro']['f1']}")
    print(f"  macro  P={m['macro']['precision']}  R={m['macro']['recall']}  F1={m['macro']['f1']}")
    print(f"  fallback={m['fallback_rate']}  avg_pred={m['avg_predicted']}  avg_gt={m['avg_gt']}")
    if "mislink" in m:
        ml = m["mislink"]
        print(f"  mislink: rate={ml['mislink_rate']} cross_vs={ml['cross_vs']} "
              f"invalid={ml['invalid']} / {ml['total_picks']} picks")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate stage selection vs Jira stage GT.")
    p.add_argument("condensed", help="condensed/index docs json (e.g. out/idmt/cosmos_idmt.json)")
    p.add_argument("--gt", default="out/stage_eval/stage_ground_truth.json")
    p.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    p.add_argument("--mode", choices=["per_vs", "one_call", "both"], default="both")
    p.add_argument("--input", choices=["summary", "raw", "both"], default="summary")
    p.add_argument("--raw-budget", type=int, default=_RAW_BUDGET_CHARS)
    p.add_argument("--count", type=int, default=0, help="limit tickets (0 = all)")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--out", default="out/stage_eval/eval_stages.runs.json")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args()))
