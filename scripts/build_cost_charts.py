"""Charts for the latency & cost EDA (docs/latency_cost_eda.md).

Measured snapshots from scripts/measure_costs.py (25 tickets, seed 13, raw text only):
  - concurrency 3 (loaded gateway) vs concurrency 1 (true per-call).
VS-selection latency from the 'evidence' eval_vs run (out/eval/evidence.runs.json).
Hardcoded on purpose - an analysis artifact, not a live recompute. Writes PNGs to docs/cost_charts/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_OUT = Path("docs/cost_charts")

# Per-call latency at concurrency 1 (true) vs concurrency 3 (queued). (avg, median, max)
SEQ = {  # --concurrency 1
    "stages": (7.1, 3.7, 25.5), "description": (6.0, 5.7, 10.1),
    "l3": (4.3, 3.9, 9.2), "business_needs": (8.3, 7.8, 17.0),
}
LOADED = {  # --concurrency 3 (only max differs materially; business_needs tail blew up)
    "stages": (7.0, 5.0, 22.0), "description": (6.6, 5.9, 17.3),
    "l3": (4.5, 4.0, 13.5), "business_needs": (8.7, 7.9, 65.8),
}
_ORDER = ["stages", "description", "l3", "business_needs"]


def per_call() -> None:
    """avg / median / max per component at concurrency 1."""
    fig, ax = plt.subplots(figsize=(8, 4.6))
    x = range(len(_ORDER))
    w = 0.26
    avg = [SEQ[c][0] for c in _ORDER]
    med = [SEQ[c][1] for c in _ORDER]
    mx = [SEQ[c][2] for c in _ORDER]
    for i, (label, vals, color) in enumerate(
        [("avg", avg, "#4C78A8"), ("median", med, "#54A24B"), ("max", mx, "#E45756")]
    ):
        bars = ax.bar([p + (i - 1) * w for p in x], vals, w, label=label, color=color)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.0f}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(list(x)); ax.set_xticklabels(_ORDER)
    ax.set_ylabel("seconds / call"); ax.set_title("Per-call latency, sequential (concurrency 1)",
                                                  fontsize=12, weight="bold")
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "per_call.png", dpi=130); plt.close(fig)


def tail_collapse() -> None:
    """business_needs max: concurrency 3 (queued) vs concurrency 1 (true)."""
    fig, ax = plt.subplots(figsize=(5.4, 4.4))
    labels = ["concurrency 3\n(loaded)", "concurrency 1\n(true)"]
    vals = [LOADED["business_needs"][2], SEQ["business_needs"][2]]
    bars = ax.bar(labels, vals, color=["#E45756", "#54A24B"])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}s", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("business_needs max latency (s)")
    ax.set_title("The 65.8s tail was gateway queueing", fontsize=12, weight="bold")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "tail_collapse.png", dpi=130); plt.close(fig)


def parallel_vs_sequential() -> None:
    """Theme-gen wall-clock vs number of approved VSs: sequential grows, parallel flat."""
    ns = list(range(1, 7))
    # sequential = description(6.0) + stages(7.1) + N*(business_needs 8.3 + l3 4.3)
    seq = [6.0 + 7.1 + n * (8.3 + 4.3) for n in ns]
    # parallel critical path = stages(7.1) + max(business_needs 8.3, l3 4.3), flat in N
    par = [7.1 + 8.3 for _ in ns]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.plot(ns, seq, "-o", color="#E45756", label="sequential (no parallelism)")
    ax.plot(ns, par, "-o", color="#54A24B", label="parallel (3 + 2N fan-out)")
    for n, s in zip(ns, seq):
        ax.text(n, s + 1, f"{s:.0f}s", ha="center", fontsize=7, color="#E45756")
    ax.text(ns[-1], par[-1] + 2, f"~{par[-1]:.0f}s flat", ha="right", fontsize=8, color="#357a30")
    ax.set_xlabel("approved Value Streams (N)"); ax.set_ylabel("theme-gen wall-clock (s)")
    ax.set_title("Parallel fan-out makes theme-gen ~flat in N", fontsize=12, weight="bold")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "parallel_vs_sequential.png", dpi=130); plt.close(fig)


def end_to_end() -> None:
    """Stacked end-to-end machine time (excludes human approval). Condense is an estimate."""
    stages = [("condense\n(est.)", 7.0, "#B0B0B0"), ("VS retrieval\n+ select", 5.2, "#9ECAE1"),
              ("theme-gen\n(parallel)", 15.4, "#54A24B")]
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    bottom = 0.0
    for label, v, c in stages:
        ax.bar(["end-to-end"], [v], bottom=bottom, color=c, label=label)
        ax.text(0, bottom + v / 2, f"{label}\n{v:.1f}s", ha="center", va="center", fontsize=8)
        bottom += v
    ax.text(0, bottom + 0.8, f"~{bottom:.0f}s model time", ha="center", fontsize=10, weight="bold")
    ax.set_ylabel("seconds (sequential pipeline stages)")
    ax.set_title("End-to-end model time (excl. HITL approval)", fontsize=12, weight="bold")
    ax.set_ylim(0, bottom + 4)
    fig.tight_layout(); fig.savefig(_OUT / "end_to_end.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    _OUT.mkdir(parents=True, exist_ok=True)
    per_call(); tail_collapse(); parallel_vs_sequential(); end_to_end()
    print(f"wrote charts to {_OUT}/")
