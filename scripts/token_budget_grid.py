"""Joint optimization: attachment cap x token budget -> ticket coverage (Task 4/5).

The question: which combination of "keep top-N attachments" and "token budget B" covers most tickets
without truncating text mid-document? This reads the EDA cache, and for each cap N computes each
ticket's tokens (description + its largest N attachments), then reports:
  - the capped token distribution per N (median / p90 / p95 / max),
  - how much of a ticket's attachment content cap-N retains (so we see what we'd be dropping),
  - a GRID of % tickets fully covered for every (cap N, budget B) pair.

Keeping the LARGEST N attachments = content-maximizing (and the worst case for fit), so the grid is
a safe lower bound on coverage. Pure-local (reads the cache), no Jira/Azure/LLM.

    uv run python -m scripts.token_budget_grid
    uv run python -m scripts.token_budget_grid --cache out/eda/attachments/attachments_raw.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

CAPS = [1, 2, 3, 4, 5, 99]                      # 99 = "all attachments"
BUDGETS = [4_000, 6_000, 8_000, 12_000, 16_000, 24_000, 32_000]


def _stats(vals: list[float]) -> dict:
    v = sorted(vals)
    n = len(v)
    return {"median": v[n // 2], "p90": v[min(n - 1, int(0.9 * n))],
            "p95": v[min(n - 1, int(0.95 * n))], "max": v[-1]} if v else {}


def main(cache_path: str, out_path: str) -> None:
    records = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    tickets: dict[str, dict] = {}
    for r in records:
        t = tickets.setdefault(r["ticketId"], {"desc": 0, "att": []})
        if r.get("kind") == "description":
            t["desc"] = int(r.get("tokenEst", 0))
        elif r.get("kind") == "attachment" and r.get("supported") and r.get("tokenEst", 0):
            t["att"].append(int(r["tokenEst"]))

    # per ticket: tokens when keeping the largest N attachments (+ description), for each cap
    capped: dict[int, list[int]] = {c: [] for c in CAPS}
    retained: dict[int, list[float]] = {c: [] for c in CAPS}
    for t in tickets.values():
        att = sorted(t["att"], reverse=True)         # largest first
        total_att = sum(att) or 0
        for c in CAPS:
            kept = sum(att[:c])
            capped[c].append(t["desc"] + kept)
            retained[c].append((kept / total_att) if total_att else 1.0)
    n = len(tickets)
    cap_label = {c: ("all" if c == 99 else str(c)) for c in CAPS}

    print(f"\n=== ATTACHMENT-CAP x TOKEN-BUDGET GRID — {n} tickets ===\n")
    print("Capped tokens per ticket (description + largest N attachments):")
    print(f"  {'cap':>4} {'median':>8} {'p90':>8} {'p95':>8} {'max':>8}  {'content kept':>13}")
    for c in CAPS:
        s = _stats(capped[c])
        keep = statistics.mean(retained[c])
        print(f"  {cap_label[c]:>4} {s['median']:>8.0f} {s['p90']:>8.0f} {s['p95']:>8.0f} "
              f"{s['max']:>8.0f}  {keep:>12.0%}")

    print(f"\nCOVERAGE GRID — % of tickets whose text FITS the budget (no truncation):\n")
    header = "  cap\\budget " + "".join(f"{b//1000:>6}k" for b in BUDGETS)
    print(header)
    grid = {}
    for c in CAPS:
        row = []
        for b in BUDGETS:
            cov = sum(1 for v in capped[c] if v <= b) / n
            row.append(cov)
        grid[cap_label[c]] = {f"{b}": round(sum(1 for v in capped[c] if v <= b) / n, 4) for b in BUDGETS}
        print(f"  {cap_label[c]:>9}  " + "".join(f"{v:>6.0%} " for v in row))

    payload = {
        "n_tickets": n,
        "capped_tokens": {cap_label[c]: {**_stats(capped[c]),
                                         "content_kept": round(statistics.mean(retained[c]), 4)} for c in CAPS},
        "coverage_grid": grid, "budgets": BUDGETS, "caps": [cap_label[c] for c in CAPS],
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nsummary -> {out}  (send me this for the write-up)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default="out/eda/attachments/attachments_raw.json")
    parser.add_argument("--out", default="out/eda/token_budget_grid.json")
    args = parser.parse_args()
    main(args.cache, args.out)
