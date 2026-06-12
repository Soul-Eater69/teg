"""Split historic coverage (recall@k) by ticket difficulty, from an existing retrieval_eval.json.

Reads the FULL retrieval_eval.json (the one with per_query) and reports, for each K, the average
fraction of GT Value Streams the historic tickets cover - split by single-VS (easy) vs multi-VS
(hard) tickets. Pure-local, no Azure/LLM, no re-run.

    uv run python scripts/retrieval_cohort.py out/eval/retrieval_eval.json
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "out/eval/retrieval_eval.json")
    pq = json.loads(path.read_text(encoding="utf-8"))["per_query"]
    single = [q for q in pq if q["gt_size"] == 1]
    multi = [q for q in pq if q["gt_size"] >= 2]
    ks = sorted({int(k) for q in pq for k in q["at_k"]})

    def recall(rows, k):
        vals = [r["at_k"][str(k)]["recall"] if str(k) in r["at_k"] else r["at_k"][k]["recall"] for r in rows]
        return statistics.mean(vals) if vals else 0.0

    def full(rows, k):
        vals = [(r["at_k"].get(str(k)) or r["at_k"][k])["recall"] >= 0.999 for r in rows]
        return statistics.mean(vals) if vals else 0.0

    print(f"tickets: {len(pq)}  (single-VS {len(single)} = {len(single)/len(pq):.0%}, "
          f"multi-VS {len(multi)} = {len(multi)/len(pq):.0%})\n")
    print(f"{'':14}" + "".join(f"  K={k:<8}" for k in ks))
    for label, rows in (("ALL tickets", pq), ("single-VS", single), ("multi-VS", multi)):
        cov = "".join(f"  {recall(rows, k):>6.1%}   " for k in ks)
        print(f"avg coverage {label:10}{cov}")
    print()
    for label, rows in (("ALL tickets", pq), ("single-VS", single), ("multi-VS", multi)):
        fc = "".join(f"  {full(rows, k):>6.1%}   " for k in ks)
        print(f"fully covered {label:9}{fc}")


if __name__ == "__main__":
    main()
