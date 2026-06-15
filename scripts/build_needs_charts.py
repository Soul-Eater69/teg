"""Charts for the business-needs EDA (docs/business_needs_eda.md).

Measured snapshots from the three business-needs runs (~145 VS docs, sample=50, seed=13).
Hardcoded - an analysis artifact. Writes PNGs to docs/needs_charts/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_OUT = Path("docs/needs_charts")

# Prompt journey: baseline -> grounding -> rebalanced -> final (GPT-5 judge). (metric, [4 values])
JOURNEY = [
    ("faithfulness", [0.735, 0.817, 0.827, 0.895]),
    ("hallucination", [0.265, 0.183, 0.173, 0.105]),
    ("coverage", [0.736, 0.633, 0.669, 0.810]),
    ("stage_align", [0.972, 0.812, 0.833, 0.855]),
]
_STAGES = ["baseline", "grounding", "rebalanced", "final\n(GPT-5)"]
_COLORS = ["#B0B0B0", "#F2A93B", "#9ECAE1", "#54A24B"]


def journey() -> None:
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    metrics = [m for m, _ in JOURNEY]
    x = range(len(metrics))
    w = 0.2
    for i, label in enumerate(_STAGES):
        vals = [vals[i] for _, vals in JOURNEY]
        bars = ax.bar([p + (i - 1.5) * w for p in x], vals, w, label=label, color=_COLORS[i])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}", ha="center", va="bottom", fontsize=6)
    ax.set_xticks(list(x)); ax.set_xticklabels(metrics)
    ax.set_ylabel("score"); ax.set_ylim(0, 1.0)
    ax.set_title("Prompt journey: grounding lifted faithfulness, rebalance recovered the rest",
                 fontsize=11, weight="bold")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "journey.png", dpi=130); plt.close(fig)


# Final locked metrics (GPT-5 judge).
FINAL = [
    ("faithfulness", 0.895), ("coverage", 0.810), ("stage_usage", 0.999), ("stage_align", 0.855),
    ("hallucination", 0.105),
]


def final() -> None:
    labels = [m for m, _ in FINAL]
    vals = [v for _, v in FINAL]
    colors = ["#E45756" if m == "hallucination" else "#54A24B" for m in labels]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    bars = ax.bar(range(len(labels)), vals, color=colors)
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("score"); ax.set_ylim(0, 1.05)
    ax.set_title("Business Needs - final metrics (raw text, reference-free)", fontsize=12, weight="bold")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "final.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    _OUT.mkdir(parents=True, exist_ok=True)
    journey(); final()
    print(f"wrote charts to {_OUT}/")
