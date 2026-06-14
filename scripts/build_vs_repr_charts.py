"""Charts for the VS representation EDA (docs/vs_representation_eda.md).

Data is the measured snapshot from the representation ladder + the raw@7k-index run
(100 gt>=3 tickets, count_mode=gt, evidence/recall/K6). Hardcoded on purpose - this is an
analysis artifact, not a live recompute. Writes PNGs to docs/vs_repr_charts/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_OUT = Path("docs/vs_repr_charts")

# (label, prompt, historic, retrieval, F1, exact_set%, latency_s, historic_lane_R)
ROWS = [
    ("all-summary", "summary", "summary", "summary", 0.715, 23, 4.2, 0.902),
    ("raw + summary", "raw", "summary", "summary", 0.786, 36, 5.8, 0.902),
    ("raw + raw@1500", "raw", "raw@1500", "summary", 0.781, 26, 5.6, 0.902),
    ("raw + raw@3000", "raw", "raw@3000", "summary", 0.768, 24, 6.3, 0.902),
    ("raw + description", "raw", "description", "summary", 0.780, 31, 4.4, 0.902),
    ("raw + raw@7k", "raw", "raw@7k", "summary", 0.780, 30, 9.4, 0.902),
    ("raw@7k INDEX", "raw", "raw@7k", "raw@7k", 0.754, 23, 13.9, 0.843),
]
_WINNER = "raw + summary"


def _bar(ax, labels, values, ylabel, title, fmt="{:.3f}", highlight=None, color="#4C78A8"):
    colors = ["#E45756" if highlight and l == highlight else color for l in labels]
    bars = ax.bar(range(len(labels)), values, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12, weight="bold")
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v, fmt.format(v), ha="center", va="bottom", fontsize=8)
    ax.grid(axis="y", alpha=0.3)


def f1_ladder() -> None:
    labels = [r[0] for r in ROWS]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    _bar(ax, labels, [r[4] for r in ROWS], "micro F1 (= P = R at count=gt)",
         "VS prediction F1 by representation (100 gt>=3 tickets)", highlight=_WINNER)
    ax.set_ylim(0.65, 0.81)
    fig.tight_layout(); fig.savefig(_OUT / "f1_ladder.png", dpi=130); plt.close(fig)


def retrieval_compare() -> None:
    # summary retrieval (winner) vs raw@7k retrieval - the historic-lane recall and the F1 it buys.
    labels = ["summary retrieval\n(raw prompt + summary historic)", "raw@7k retrieval\n(all raw)"]
    f1 = [0.786, 0.754]
    hist = [0.902, 0.843]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 4.4))
    _bar(a1, labels, hist, "historic-lane recall", "Retrieval quality\n(did precedent surface GT?)",
         color="#54A24B")
    a1.set_ylim(0.7, 0.95)
    _bar(a2, labels, f1, "micro F1", "Resulting F1", color="#4C78A8")
    a2.set_ylim(0.7, 0.81)
    fig.tight_layout(); fig.savefig(_OUT / "retrieval_compare.png", dpi=130); plt.close(fig)


def latency() -> None:
    labels = [r[0] for r in ROWS]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    _bar(ax, labels, [r[6] for r in ROWS], "avg prediction latency (s)",
         "Latency by representation (LLM prompt size drives it)", fmt="{:.1f}s",
         highlight="raw@7k INDEX", color="#72B7B2")
    fig.tight_layout(); fig.savefig(_OUT / "latency.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    _OUT.mkdir(parents=True, exist_ok=True)
    f1_ladder(); retrieval_compare(); latency()
    print(f"wrote charts to {_OUT}/")
