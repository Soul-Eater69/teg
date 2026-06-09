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

from teg.bootstrap import build_value_stream_service
from teg.contracts.value_stream_io import ValueStreamRequest
from teg.domain.condensed import SummaryFields
from teg.value_stream.config import ValueStreamConfig


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


async def _eval_one(service, args, doc, ticket_id: str, gt: set[str], sem, progress) -> dict:
    async with sem:
        request = ValueStreamRequest(
            ticket_id=ticket_id,
            summary_fields=_summary_fields(doc.get("properties", {}), raw_text=args.raw_text),
            requested_count=_requested_count(args, gt),
            exclude_ticket_ids=[ticket_id],  # leave-one-out
        )
        try:
            resp = await service.predict(request)
            predicted = [r.value_stream_id for r in resp.recommendations]
        except Exception as exc:  # one bad ticket must not abort the batch
            progress["done"] += 1
            print(f"[{progress['done']}/{progress['total']}] {ticket_id}  ERROR {type(exc).__name__}: {exc}")
            return {"ticket_id": ticket_id, "gt": gt, "predicted": [], "error": str(exc)}
    tp, fp, fn = _prf(predicted, gt)
    progress["done"] += 1
    print(f"[{progress['done']}/{progress['total']}] {ticket_id}  "
          f"P={_div(tp, tp+fp):.2f} R={_div(tp, tp+fn):.2f}  (gt={len(gt)}, pred={len(predicted)})")
    return {"ticket_id": ticket_id, "gt": gt, "predicted": predicted}


async def main(args) -> None:
    docs = _load(args.dataset)
    config = ValueStreamConfig(use_historic_classification=not args.no_classification)
    service = build_value_stream_service(config=config)

    jobs = []
    for i, doc in enumerate(docs, start=1):
        gt = _gt_ids(doc.get("properties", {}))
        if gt:
            jobs.append((doc, doc.get("sourceId") or doc.get("id") or f"row{i}", gt))

    sem = asyncio.Semaphore(args.concurrency)
    progress = {"done": 0, "total": len(jobs)}
    print(f"evaluating {len(jobs)} tickets (concurrency={args.concurrency})")
    results = await asyncio.gather(*(_eval_one(service, args, d, t, g, sem, progress) for d, t, g in jobs))

    rows: list[dict] = []
    micro_tp = micro_fp = micro_fn = 0
    p_at = {k: [] for k in args.k}
    r_at = {k: [] for k in args.k}
    for res in results:
        if res.get("error"):
            continue
        gt, predicted = res["gt"], res["predicted"]
        tp, fp, fn = _prf(predicted, gt)
        micro_tp += tp; micro_fp += fp; micro_fn += fn
        for k in args.k:
            topk = set(predicted[:k])
            p_at[k].append(_div(len(topk & gt), min(k, len(predicted)) or 1))
            r_at[k].append(_div(len(topk & gt), len(gt)))
        rows.append({
            "ticket_id": res["ticket_id"], "gt_count": len(gt), "predicted_count": len(predicted),
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(_div(tp, tp + fp), 3), "recall": round(_div(tp, tp + fn), 3),
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
          f"input={'rawText' if args.raw_text else 'condensed'})")
    print(f"micro  P={micro_p:.3f}  R={micro_r:.3f}  F1={_div(2*micro_p*micro_r, micro_p+micro_r):.3f}")
    print(f"macro  P={macro_p:.3f}  R={macro_r:.3f}  F1={_div(2*macro_p*macro_r, macro_p+macro_r):.3f}")
    for k in args.k:
        print(f"  @{k:<2}  P@{k}={_div(sum(p_at[k]), n):.3f}   R@{k}={_div(sum(r_at[k]), n):.3f}")

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
    parser.add_argument("--k", type=int, nargs="+", default=[3, 5, 10], help="k values for P@k / R@k")
    parser.add_argument("--concurrency", type=int, default=6, help="tickets evaluated in parallel")
    parser.add_argument("--no-classification", action="store_true", help="ablation: ignore direct/implied")
    parser.add_argument("--raw-text", action="store_true", help="use rawText instead of summaryFields")
    parser.add_argument("--out", default="out/eval/vs_eval.csv")
    args = parser.parse_args()
    asyncio.run(main(args))
