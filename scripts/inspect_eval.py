"""Inspect a generative-eval CSV: surface the failure cohorts with the offending text.

Don't lock on aggregates - read the cases. Given an eval CSV (eval_description.csv or
eval_business_needs.csv) this pulls the rows that matter, so you can judge whether a low metric is a
real problem or metric noise:

  1. conservative   : coverage low BUT faithfulness high -> the model omitted detail (shows missed_facts)
  2. misaligned     : stage_align below 1 -> needs filed under the wrong stage (shows the why-notes)
  3. hallucinating  : hallucination above a threshold -> shows the unsupported claims to judge if real

Usage:
  uv run python scripts/inspect_eval.py out/needs_eval/eval_business_needs.csv
  uv run python scripts/inspect_eval.py out/desc_eval/eval_description.csv --top 8
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _f(row: dict, key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except ValueError:
        return 0.0


def _print(title: str, rows: list[dict], cols: list[str]) -> None:
    print(f"\n{'=' * 70}\n{title}  ({len(rows)} rows)\n{'=' * 70}")
    for r in rows:
        head = f"{r.get('ticket_id', '?')} / {r.get('value_stream_id', '?')}"
        nums = "  ".join(f"{c}={r.get(c)}" for c in ("faithfulness", "coverage", "stage_align")
                         if c in r and r.get(c))
        print(f"\n- {head}   {nums}")
        for c in cols:
            val = (r.get(c) or "").strip()
            if val:
                print(f"    {c}: {val}")


def main(args: argparse.Namespace) -> None:
    rows = list(csv.DictReader(Path(args.csv).open(encoding="utf-8")))
    if not rows:
        raise SystemExit("empty CSV")
    has = rows[0].keys()

    # 1. conservative: high faithfulness, low coverage (omitting detail, not inventing).
    conservative = sorted(
        [r for r in rows if _f(r, "faithfulness") >= args.faith_high and _f(r, "coverage") <= args.cov_low],
        key=lambda r: _f(r, "coverage"))[:args.top]
    _print(f"1. CONSERVATIVE  (faithfulness >= {args.faith_high}, coverage <= {args.cov_low})",
           conservative, [c for c in ("missed_facts",) if c in has])

    # 2. misaligned stages (business needs only).
    if "stage_align" in has:
        misaligned = sorted([r for r in rows if 0 < _f(r, "stage_align") < 1.0
                             or (r.get("misaligned_stages") or "").strip()],
                            key=lambda r: _f(r, "stage_align"))[:args.top]
        _print("2. MISALIGNED STAGES  (stage_align < 1.0; needs filed under the wrong stage)",
               misaligned, [c for c in ("misaligned_stages", "unused_stages") if c in has])

    # 3. hallucinating: hallucination above threshold -> read the unsupported claims.
    hallu = sorted([r for r in rows if _f(r, "hallucination") >= args.hallu],
                   key=lambda r: -_f(r, "hallucination"))[:args.top]
    _print(f"3. HALLUCINATING  (hallucination >= {args.hallu}) - are these real or metric noise?",
           hallu, [c for c in ("unsupported",) if c in has])

    print(f"\n{'=' * 70}")
    print(f"totals: {len(rows)} rows | conservative {len(conservative)} | "
          f"hallucination>={args.hallu}: {sum(1 for r in rows if _f(r, 'hallucination') >= args.hallu)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Surface generative-eval failure cohorts with the text.")
    p.add_argument("csv", help="eval_description.csv or eval_business_needs.csv")
    p.add_argument("--faith-high", type=float, default=0.85, help="'high faithfulness' threshold")
    p.add_argument("--cov-low", type=float, default=0.6, help="'low coverage' threshold")
    p.add_argument("--hallu", type=float, default=0.15, help="'hallucinating' threshold")
    p.add_argument("--top", type=int, default=10, help="rows per cohort")
    main(p.parse_args())
