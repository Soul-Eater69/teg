"""Batch evaluation of Value Stream prediction against the historic ground truth.

Dataset = the ingested Cosmos IDMT docs (out/idmt/cosmos_idmt.json): each carries the
condensed summaryFields (input) and its approved VS ground truth (properties.themes[]).

Per ticket: run prediction, EXCLUDING the ticket itself from the historic analog lane
(leave-one-out - a ticket must not see its own GT). Compare the predicted VS ids against
the GT ids. Reports precision / recall / F1 (micro + macro) and precision@k / recall@k.

Experiments:
  (default)            condensed summaryFields, with direct/implied classification
  --no-classification  ablation: ignore the historic direct/implied label
  --raw-text           feed properties.rawText as the query instead of summaryFields

Usage:
  uv run python -m scripts.eval_vs out/idmt/cosmos_idmt.json --count 10 --k 3 5 10
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path
from time import perf_counter

from teg.bootstrap import build_value_stream_service
from teg.config.settings import load_settings
from teg.contracts.value_stream_io import ValueStreamRequest
from teg.domain.condensed import SummaryFields
from teg.integrations.llm import build_llm_client
from teg.value_stream.config import ValueStreamConfig
from teg.value_stream.drop_explainer import explain_drops
from teg.value_stream.relevance_judge import judge_value_streams


def _load(path: str) -> list[dict]:
    docs = json.loads(Path(path).read_text(encoding="utf-8"))
    return docs if isinstance(docs, list) else [docs]


def _summary_fields(props: dict, *, raw_text: bool) -> SummaryFields:
    if raw_text:
        text = props.get("rawText", "") or props.get("summary", "")
        return SummaryFields(generated_summary=text, business_problem="", business_capability="")
    return SummaryFields(
        generated_summary=props.get("summary", ""),
        business_problem=props.get("businessProblem", ""),
        business_capability=props.get("businessCapability", ""),
        key_terms=props.get("keyTerms", []) or [],
        stakeholders=props.get("stakeholders", []) or [],
        systems_and_products=props.get("systemsAndProducts", []) or [],
    )


def _gt_ids(props: dict) -> set[str]:
    return {t["valueStreamId"] for t in (props.get("themes") or []) if t.get("valueStreamId")}


def _vs_name_map(docs: list[dict]) -> dict[str, str]:
    names: dict[str, str] = {}
    for doc in docs:
        for t in doc.get("properties", {}).get("themes") or []:
            if t.get("valueStreamId"):
                names[t["valueStreamId"]] = t.get("valueStreamName") or t["valueStreamId"]
    return names


def _base_rate_counts(docs: list[dict]) -> tuple[dict[str, int], int]:
    """Corpus tag frequency: how many tickets carry each VS as GT, and the ticket total.

    The 'breadth' prior - a VS tagged on many tickets is broad/generic. Built once over the
    whole corpus; the per-ticket rate is computed leave-one-out so a ticket never informs its
    own penalty.
    """
    counts: dict[str, int] = {}
    total = 0
    for doc in docs:
        gt = _gt_ids(doc.get("properties", {}))
        if not gt:
            continue
        total += 1
        for vs in gt:
            counts[vs] = counts.get(vs, 0) + 1
    return counts, total


def _loo_base_rates(counts: dict[str, int], total: int, gt: set[str]) -> dict[str, float]:
    """Per-ticket base rate excluding this ticket's own tags (leave-one-out)."""
    denom = max(1, total - 1)
    return {vs: (n - (1 if vs in gt else 0)) / denom for vs, n in counts.items()}


async def _collect_predictions(service, args, jobs, sem) -> dict[str, list[str]]:
    """Pass 1: predict every ticket with the penalty OFF, to measure each stream's FP-rate."""
    async def _one(doc, ticket_id, gt):
        async with sem:
            req = ValueStreamRequest(
                ticket_id=ticket_id,
                summary_fields=_summary_fields(doc.get("properties", {}), raw_text=args.raw_text),
                requested_count=_requested_count(args, gt),
                exclude_ticket_ids=[ticket_id],
            )
            try:
                resp, _ = await service.predict_traced(req, base_rates={})  # {} = no penalty
                return ticket_id, [r.value_stream_id for r in resp.recommendations]
            except Exception:
                return ticket_id, []
    print(f"FP-rate prior: pass 1 predicting {len(jobs)} tickets (penalty off)...")
    pairs = await asyncio.gather(*(_one(d, t, g) for d, t, g, _ in jobs))
    return dict(pairs)


def _fp_rate_stats(pred_by_ticket: dict[str, list[str]], gt_by_ticket: dict[str, set[str]]):
    """Per-VS (predicted_count, false_positive_count) across the corpus + the per-ticket views."""
    pred_count: dict[str, int] = {}
    fp_count: dict[str, int] = {}
    for tid, preds in pred_by_ticket.items():
        gt = gt_by_ticket.get(tid, set())
        for vs in set(preds):
            pred_count[vs] = pred_count.get(vs, 0) + 1
            if vs not in gt:
                fp_count[vs] = fp_count.get(vs, 0) + 1
    return pred_count, fp_count


def _loo_fp_rates(pred_count, fp_count, ticket_preds: list[str], gt: set[str]) -> dict[str, float]:
    """Per-ticket FP-rate prior, leave-one-out (Laplace-smoothed so rarely-predicted ~0.5).

    fp_rate = (this stream's false positives) / (times it was predicted). High = attractor.
    """
    preds = set(ticket_preds)
    rates: dict[str, float] = {}
    for vs, p in pred_count.items():
        p_loo = p - (1 if vs in preds else 0)
        fp_loo = fp_count.get(vs, 0) - (1 if (vs in preds and vs not in gt) else 0)
        rates[vs] = (fp_loo + 1) / (p_loo + 2)  # smoothed; neutral 0.5 when unseen
    return rates


def _prf(predicted: list[str], gt: set[str]) -> tuple[int, int, int]:
    pset = set(predicted)
    tp = len(pset & gt)
    return tp, len(pset) - tp, len(gt) - tp  # tp, fp, fn


def _div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _requested_count(args, gt: set[str]) -> int:
    if args.count_mode == "gt":
        return max(1, len(gt))
    if args.count_mode == "gt_buffer":
        return max(1, len(gt) + args.buffer)
    return args.count


async def _eval_one(service, llm, args, doc, ticket_id: str, gt: set[str], base_rates, vs_names, sem, progress) -> dict:
    async with sem:
        request = ValueStreamRequest(
            ticket_id=ticket_id,
            summary_fields=_summary_fields(doc.get("properties", {}), raw_text=args.raw_text),
            requested_count=_requested_count(args, gt),
            exclude_ticket_ids=[ticket_id],  # leave-one-out
        )
        try:
            t0 = perf_counter()
            resp, trace = await service.predict_traced(request, base_rates=base_rates)
            elapsed = perf_counter() - t0  # prediction latency only (excludes judge/explain probes)
            predicted = [r.value_stream_id for r in resp.recommendations]
        except Exception as exc:  # one bad ticket must not abort the batch
            progress["done"] += 1
            print(f"[{progress['done']}/{progress['total']}] {ticket_id}  ERROR {type(exc).__name__}: {exc}")
            return {"ticket_id": ticket_id, "gt": gt, "predicted": [], "error": str(exc)}
        buckets = _miss_buckets(gt, predicted, trace)
        # Post-hoc: ask why the LLM dropped GT it actually saw (never changes the metrics).
        drop_reasons: dict[str, str] = {}
        if llm is not None and buckets["llm_dropped"]:
            try:
                explained = await explain_drops(
                    query=request.summary_fields.generated_summary,
                    review_pool=trace.review_pool,
                    picked_ids=predicted,
                    dropped_ids=buckets["llm_dropped"],
                    llm_client=llm,
                )
                drop_reasons = {vs: exp.reason_code for vs, exp in explained.items()}
            except Exception as exc:  # a failed probe must not abort the batch
                print(f"    explain-drops failed for {ticket_id}: {type(exc).__name__}: {exc}")
        # LLM-as-judge: is each predicted / missed VS genuinely relevant (independent of GT)?
        judged: dict[str, bool] = {}
        if llm is not None and args.judge:
            try:
                pool_desc = {c.value_stream_id: c.value_stream_description for c in trace.review_pool}
                name_of = {**vs_names, **{r.value_stream_id: r.value_stream_name for r in resp.recommendations}}
                ids = set(predicted) | gt
                items = [(i, name_of.get(i, i), pool_desc.get(i, "")) for i in ids]
                judged = await judge_value_streams(
                    query=request.summary_fields.generated_summary, items=items, llm_client=llm
                )
            except Exception as exc:
                print(f"    judge failed for {ticket_id}: {type(exc).__name__}: {exc}")
    tp, fp, fn = _prf(predicted, gt)
    progress["done"] += 1
    print(f"[{progress['done']}/{progress['total']}] {ticket_id}  "
          f"P={_div(tp, tp+fp):.2f} R={_div(tp, tp+fn):.2f}  (gt={len(gt)}, pred={len(predicted)}, {elapsed:.1f}s)")
    return {"ticket_id": ticket_id, "gt": gt, "predicted": predicted,
            "buckets": buckets, "drop_reasons": drop_reasons, "judged": judged, "elapsed": elapsed}


def _miss_buckets(gt: set[str], predicted: list[str], trace) -> dict[str, list[str]]:
    """Localize each FN: where did the right answer die?

    not_retrieved  -> never made the merged candidate set (retrieval gap)
    gated_pre_llm  -> retrieved, but the merger dropped it before the LLM saw it
    llm_dropped    -> the LLM saw it in the review pool and still didn't pick it
    """
    retrieved = set(trace.retrieved_ids)
    pool = set(trace.review_pool_ids)
    out: dict[str, list[str]] = {"not_retrieved": [], "gated_pre_llm": [], "llm_dropped": []}
    for vs in gt - set(predicted):
        if vs not in retrieved:
            out["not_retrieved"].append(vs)
        elif vs not in pool:
            out["gated_pre_llm"].append(vs)
        else:
            out["llm_dropped"].append(vs)
    return out


async def main(args) -> None:
    docs = _load(args.dataset)
    config = ValueStreamConfig(
        use_historic_classification=not args.no_classification,
        use_historic_lane=not args.semantic_only,
        generic_penalty_scale=args.generic_penalty,
        **({"llm_candidate_window": args.window} if args.window else {}),
    )
    service = build_value_stream_service(config=config)
    llm = build_llm_client(load_settings()) if (args.explain_drops or args.judge) else None
    sem = asyncio.Semaphore(args.concurrency)

    vs_names = _vs_name_map(docs)  # id -> name, for judging GT streams not in the pool
    base_jobs = []
    skipped = 0
    for i, doc in enumerate(docs, start=1):
        gt = _gt_ids(doc.get("properties", {}))
        if len(gt) < args.min_gt:  # drop tickets with too few GT VS (e.g. single-label)
            skipped += 1
            continue
        base_jobs.append((doc, doc.get("sourceId") or doc.get("id") or f"row{i}", gt))

    # Build the per-ticket penalty prior (leave-one-out) from the chosen signal.
    #   gt_freq = corpus tag frequency (broad = often a GT). fp_rate = false-positive rate
    #   (broad = often predicted-but-wrong; the correct attractor signal, needs a pass 1).
    rate_for: dict[str, dict[str, float] | None] = {t: None for _, t, _ in base_jobs}
    if args.generic_penalty > 0:
        if args.penalty_signal == "fp_rate":
            gt_by = {t: g for _, t, g in base_jobs}
            preds = await _collect_predictions(service, args, [(d, t, g, None) for d, t, g in base_jobs], sem)
            pred_count, fp_count = _fp_rate_stats(preds, gt_by)
            for _, t, g in base_jobs:
                rate_for[t] = _loo_fp_rates(pred_count, fp_count, preds.get(t, []), g)
        else:
            counts, total = _base_rate_counts(docs)
            for _, t, g in base_jobs:
                rate_for[t] = _loo_base_rates(counts, total, g)

    jobs = [(d, t, g, rate_for[t]) for d, t, g in base_jobs]
    progress = {"done": 0, "total": len(jobs)}
    print(f"evaluating {len(jobs)} tickets (concurrency={args.concurrency}; "
          f"skipped {skipped} with < {args.min_gt} GT value streams; "
          f"penalty={args.generic_penalty} signal={args.penalty_signal})")
    try:
        results = await asyncio.gather(
            *(_eval_one(service, llm, args, d, t, g, r, vs_names, sem, progress) for d, t, g, r in jobs)
        )
    finally:
        await service.aclose()
        if llm is not None and hasattr(llm, "aclose"):
            await llm.aclose()

    rows: list[dict] = []
    micro_tp = micro_fp = micro_fn = 0
    bucket_totals = {"not_retrieved": 0, "gated_pre_llm": 0, "llm_dropped": 0}
    reason_totals: dict[str, int] = {}
    # Judge-adjusted: predictions judged relevant (even if not GT) + misses judged supported.
    judge_pred = judge_rel_pred = judge_supported_miss = 0
    p_at = {k: [] for k in args.k}
    r_at = {k: [] for k in args.k}
    for res in results:
        if res.get("error"):
            continue
        gt, predicted = res["gt"], res["predicted"]
        tp, fp, fn = _prf(predicted, gt)
        micro_tp += tp; micro_fp += fp; micro_fn += fn
        judged = res.get("judged") or {}
        if judged:
            judge_pred += len(predicted)
            judge_rel_pred += sum(1 for p in predicted if judged.get(p))
            judge_supported_miss += sum(1 for g in gt if g not in predicted and judged.get(g))
        buckets = res.get("buckets") or {}
        for name in bucket_totals:
            bucket_totals[name] += len(buckets.get(name, []))
        drop_reasons = res.get("drop_reasons") or {}
        for code in drop_reasons.values():
            reason_totals[code] = reason_totals.get(code, 0) + 1
        for k in args.k:
            topk = set(predicted[:k])
            p_at[k].append(_div(len(topk & gt), min(k, len(predicted)) or 1))
            r_at[k].append(_div(len(topk & gt), len(gt)))
        rows.append({
            "ticket_id": res["ticket_id"], "gt_count": len(gt), "predicted_count": len(predicted),
            "tp": tp, "fp": fp, "fn": fn, "seconds": round(res.get("elapsed", 0.0), 2),
            "precision": round(_div(tp, tp + fp), 3), "recall": round(_div(tp, tp + fn), 3),
            "fn_not_retrieved": "; ".join(buckets.get("not_retrieved", [])),
            "fn_gated_pre_llm": "; ".join(buckets.get("gated_pre_llm", [])),
            "fn_llm_dropped": "; ".join(buckets.get("llm_dropped", [])),
            "fn_drop_reasons": "; ".join(f"{vs}={code}" for vs, code in drop_reasons.items()),
            "gt": "; ".join(sorted(gt)), "predicted": "; ".join(predicted),
        })

    n = len(rows)
    micro_p = _div(micro_tp, micro_tp + micro_fp)
    micro_r = _div(micro_tp, micro_tp + micro_fn)
    macro_p = _div(sum(r["precision"] for r in rows), n)
    macro_r = _div(sum(r["recall"] for r in rows), n)

    print("\n" + "=" * 60)
    print(f"tickets evaluated: {n}   "
          f"(count_mode={args.count_mode}, classification={'OFF' if args.no_classification else 'ON'}, "
          f"input={'rawText' if args.raw_text else 'condensed'}, window={args.window or 18}, "
          f"generic_penalty={args.generic_penalty}/{args.penalty_signal if args.generic_penalty else '-'})")
    print(f"micro  P={micro_p:.3f}  R={micro_r:.3f}  F1={_div(2*micro_p*micro_r, micro_p+micro_r):.3f}  (strict GT)")
    print(f"macro  P={macro_p:.3f}  R={macro_r:.3f}  F1={_div(2*macro_p*macro_r, macro_p+macro_r):.3f}  (strict GT)")
    for k in args.k:
        print(f"  @{k:<2}  P@{k}={_div(sum(p_at[k]), n):.3f}   R@{k}={_div(sum(r_at[k]), n):.3f}")

    times = sorted(r["seconds"] for r in rows if r["seconds"] > 0)
    if times:
        slow = min(rows, key=lambda r: -r["seconds"])
        fast = min(rows, key=lambda r: r["seconds"] if r["seconds"] > 0 else 1e9)
        print(f"\nprediction latency (per ticket, excludes judge/explain):")
        print(f"  avg={_div(sum(times), len(times)):.1f}s   "
              f"min={fast['seconds']:.1f}s ({fast['ticket_id']})   "
              f"max={slow['seconds']:.1f}s ({slow['ticket_id']})   "
              f"median={times[len(times)//2]:.1f}s")

    if judge_pred:
        # Judge precision: predictions the LLM judge calls relevant (credits relevant non-GT picks).
        # Judge recall: TP / (TP + misses the judge says are genuinely supported) - drops GT label noise.
        adj_p = _div(judge_rel_pred, judge_pred)
        adj_r = _div(micro_tp, micro_tp + judge_supported_miss)
        print(f"judge  P={adj_p:.3f}  R={adj_r:.3f}  F1={_div(2*adj_p*adj_r, adj_p+adj_r):.3f}  "
              f"(LLM relevance; {judge_rel_pred}/{judge_pred} preds relevant, "
              f"{judge_supported_miss} of {micro_fn} misses judged supported)")

    total_fn = sum(bucket_totals.values())
    print(f"\nmiss buckets (where the {total_fn} missed GT value streams died):")
    print(f"  not_retrieved  {bucket_totals['not_retrieved']:4}  "
          f"({_div(bucket_totals['not_retrieved'], total_fn):.0%})  - never made the candidate set")
    print(f"  gated_pre_llm  {bucket_totals['gated_pre_llm']:4}  "
          f"({_div(bucket_totals['gated_pre_llm'], total_fn):.0%})  - merger dropped before the LLM")
    print(f"  llm_dropped    {bucket_totals['llm_dropped']:4}  "
          f"({_div(bucket_totals['llm_dropped'], total_fn):.0%})  - LLM saw it, didn't pick it")

    if reason_totals:
        explained = sum(reason_totals.values())
        print(f"\nwhy the LLM dropped them (of {explained} llm_dropped explained):")
        for code, cnt in sorted(reason_totals.items(), key=lambda kv: -kv[1]):
            print(f"  {code:24} {cnt:4}  ({_div(cnt, explained):.0%})")
    elif args.explain_drops and bucket_totals["llm_dropped"]:
        print(f"\n[!] --explain-drops was on and {bucket_totals['llm_dropped']} GT were llm_dropped, "
              "but the probe returned no reasons - check the explain-drops failure lines above.")
    elif bucket_totals["llm_dropped"]:
        print(f"\n[i] {bucket_totals['llm_dropped']} GT were llm_dropped but not explained - "
              "re-run with --explain-drops to classify why.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"\nper-ticket CSV -> {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="cosmos_idmt.json (ingested IDMT docs with GT)")
    parser.add_argument("--count", type=int, default=10, help="value streams to request (fixed mode)")
    parser.add_argument("--count-mode", choices=["fixed", "gt", "gt_buffer"], default="fixed",
                        help="fixed=--count; gt=|GT| per ticket (R-precision); gt_buffer=|GT|+buffer")
    parser.add_argument("--buffer", type=int, default=2, help="added to |GT| in gt_buffer mode")
    parser.add_argument("--min-gt", type=int, default=2, help="skip tickets with fewer than this many GT value streams")
    parser.add_argument("--k", type=int, nargs="+", default=[3, 5, 10], help="k values for P@k / R@k")
    parser.add_argument("--concurrency", type=int, default=6, help="tickets evaluated in parallel")
    parser.add_argument("--no-classification", action="store_true", help="ablation: ignore direct/implied")
    parser.add_argument("--semantic-only", action="store_true", help="ablation: drop the historic lane entirely")
    parser.add_argument("--raw-text", action="store_true", help="use rawText instead of summaryFields")
    parser.add_argument("--window", type=int, default=0,
                        help="override the LLM review-pool size (how many candidates the LLM sees; "
                             "default config=18). Decoupled from output count, so count=gt stays honest.")
    parser.add_argument("--generic-penalty", type=float, default=0.6,
                        help="broad-stream rank penalty scale (penalty = scale * signal, unless earned "
                             "by history). Default 0.6. Pass 0 to disable. Signal is leave-one-out.")
    parser.add_argument("--penalty-signal", choices=["fp_rate", "gt_freq"], default="fp_rate",
                        help="fp_rate = false-positive rate (correct attractor signal, runs a pass 1); "
                             "gt_freq = corpus GT frequency (penalizes common-true streams - usually wrong).")
    parser.add_argument("--explain-drops", action="store_true",
                        help="post-hoc LLM probe: classify why each llm_dropped GT was left out (extra calls)")
    parser.add_argument("--judge", action="store_true",
                        help="LLM-as-judge relevance of predictions + misses (GT-independent view; extra calls)")
    parser.add_argument("--out", default="out/eval/vs_eval.csv")
    args = parser.parse_args()
    asyncio.run(main(args))
