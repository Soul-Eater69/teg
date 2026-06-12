"""How many Value Streams (ground truth) does each ticket have? Pure-local, no Azure/LLM.

Reads the ingested IDMT docs (GT reconstructed from the sibling themes file) and prints the
distribution of GT Value-Stream count per ticket: single-VS (==1) vs multi-VS (>=2), plus a
histogram and the mean/median.

    uv run python -m scripts.gt_distribution out/idmt/cosmos_idmt.json
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter

from scripts.eval_vs import _gt_ids, _load


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "out/idmt/cosmos_idmt.json"
    docs = _load(path)
    sizes = [len(_gt_ids(d.get("properties", {}))) for d in docs]
    sizes = [s for s in sizes if s >= 1]  # tickets that have GT at all
    n = len(sizes)
    single = sum(1 for s in sizes if s == 1)
    multi = sum(1 for s in sizes if s >= 2)
    print(f"tickets with GT: {n}")
    print(f"  single-VS (exactly 1): {single:>4}  ({single / n:.0%})")
    print(f"  multi-VS  (2 or more): {multi:>4}  ({multi / n:.0%})")
    print(f"  mean {statistics.mean(sizes):.2f}  median {statistics.median(sizes)}  max {max(sizes)}")
    print("\nVS-count histogram (how many tickets have N value streams):")
    for size, count in sorted(Counter(sizes).items()):
        bar = "#" * round(count / max(Counter(sizes).values()) * 40)
        print(f"  {size:>2} VS  {count:>4}  {bar}")


if __name__ == "__main__":
    main()
