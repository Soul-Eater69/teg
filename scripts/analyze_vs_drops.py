"""Level A: why the LLM drops GT it saw - displacement / bias, from the per-ticket eval CSV.

No LLM, no eval run: reads the gt/predicted columns the eval already wrote (e.g. out/eval/drops.csv,
which must be from a count=gt run so every drop is a swap) and reports the SYSTEMATIC pattern behind
the 'lower_priority' bucket - which value streams are chronically dropped, which are over-picked, the
top 'GT-X dropped -> Y picked instead' confusions, and whether the model defaults to popular/generic
value streams. Value-stream names + corpus base rates come from the dataset / catalogue.

Usage:
  uv run python scripts/analyze_vs_drops.py out/eval/drops.csv
  uv run python scripts/analyze_vs_drops.py out/eval/drops.csv --dataset out/idmt/cosmos_idmt.json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from teg.value_stream.drop_analysis import analyze_drops


def _split(cell: str) -> list[str]:
    return [p.strip() for p in (cell or "").split(";") if p.strip()]


def _read_tickets(csv_path: Path) -> list[tuple[set[str], list[str]]]:
    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if "gt" not in (reader.fieldnames or []) or "predicted" not in (reader.fieldnames or []):
            raise SystemExit(f"{csv_path}: needs 'gt' and 'predicted' columns (a per-ticket eval CSV)")
        return [(set(_split(r["gt"])), _split(r["predicted"])) for r in reader]


def _names_and_base_rates(dataset: str | None) -> tuple[dict[str, str], dict[str, float]]:
    """{vs_id: name} and {vs_id: corpus base rate} from the ingested dataset's themes GT."""
    if not dataset or not Path(dataset).exists():
        return {}, {}
    docs = json.loads(Path(dataset).read_text(encoding="utf-8"))
    names: dict[str, str] = {}
    counts: Counter = Counter()
    total = 0
    for d in docs:
        themes = (d.get("properties") or {}).get("themes") or []
        ids = {t.get("valueStreamId") for t in themes if t.get("valueStreamId")}
        if not ids:
            continue
        total += 1
        for t in themes:
            if t.get("valueStreamId"):
                names[t["valueStreamId"]] = t.get("valueStreamName") or t["valueStreamId"]
        for vs in ids:
            counts[vs] += 1
    base = {vs: c / total for vs, c in counts.items()} if total else {}
    return names, base


def _label(vs: str, names: dict[str, str]) -> str:
    name = names.get(vs, "")
    return f"{name} ({vs})" if name else vs


def main(args: argparse.Namespace) -> None:
    tickets = _read_tickets(Path(args.csv))
    names, base_rates = _names_and_base_rates(args.dataset)
    a = analyze_drops(tickets, base_rates=base_rates)

    print(f"\n{a.n_tickets} tickets | {a.total_fn} dropped GT (FN) = {a.total_fp} wrong picks (FP) "
          f"(equal at count=gt - every drop is a swap)\n")

    print("MOST-DROPPED value streams (GT the LLM most often fails to pick; >=3 GT appearances):")
    print(f"  {'drop%':>6} {'fn/gt':>7}  value stream")
    for s in a.most_dropped(args.top):
        print(f"  {s.drop_rate:6.0%} {f'{s.fn_count}/{s.gt_count}':>7}  {_label(s.vs_id, names)}")

    print("\nMOST OVER-PICKED value streams (picked when NOT GT; the model's default reaches):")
    print(f"  {'fp':>4} {'over%':>6} {'base%':>6}  value stream")
    for s in a.most_overpicked(args.top):
        br = base_rates.get(s.vs_id, 0.0)
        print(f"  {s.fp_count:4} {s.over_rate:6.0%} {br:6.0%}  {_label(s.vs_id, names)}")

    print("\nTOP CONFUSIONS (GT dropped  ->  picked instead):")
    for (dropped, picked), n in a.top_confusions(args.top):
        print(f"  {n:3}x  {_label(dropped, names)}  ->  {_label(picked, names)}")

    if base_rates:
        print(f"\nPOPULARITY BIAS (corpus base rate, mean):")
        print(f"  dropped GT      : {a.mean_base_rate_dropped:.1%}")
        print(f"  wrong picks     : {a.mean_base_rate_overpicked:.1%}")
        verdict = ("the model swaps specific GT for more-common value streams (generic/popularity bias)"
                   if a.mean_base_rate_overpicked > a.mean_base_rate_dropped + 0.02
                   else "no strong popularity bias - drops and wrong picks are similarly common")
        print(f"  -> {verdict}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "n_tickets": a.n_tickets, "total_fn": a.total_fn, "total_fp": a.total_fp,
            "mean_base_rate_dropped": a.mean_base_rate_dropped,
            "mean_base_rate_overpicked": a.mean_base_rate_overpicked,
            "most_dropped": [{"vs": _label(s.vs_id, names), "drop_rate": round(s.drop_rate, 3),
                              "fn": s.fn_count, "gt": s.gt_count} for s in a.most_dropped(50)],
            "most_overpicked": [{"vs": _label(s.vs_id, names), "fp": s.fp_count,
                                 "base_rate": round(base_rates.get(s.vs_id, 0.0), 3)}
                                for s in a.most_overpicked(50)],
            "top_confusions": [{"dropped": _label(d, names), "picked": _label(p, names), "n": n}
                               for (d, p), n in a.top_confusions(50)],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n-> {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Displacement/bias analysis of dropped GT (Level A).")
    p.add_argument("csv", help="per-ticket eval CSV (count=gt run; needs gt + predicted columns)")
    p.add_argument("--dataset", default="out/idmt/cosmos_idmt.json", help="for VS names + base rates")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--out", default="out/eval/drop_analysis.json")
    main(p.parse_args())
