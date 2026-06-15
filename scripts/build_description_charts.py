"""Charts for the description-generation EDA (docs/description_eda.md).

Measured snapshot from the two description runs (135 VS descriptions, sample=50, seed=13).
Hardcoded - an analysis artifact, not a live recompute. Writes PNGs to docs/description_charts/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_OUT = Path("docs/description_charts")

# (metric, before prompt fix, after prompt fix)
RUNS = [
    ("faithfulness", 0.860, 0.940),
    ("coverage", 0.843, 0.774),
    ("hallucination", 0.140, 0.060),
]


def before_after() -> None:
    labels = [r[0] for r in RUNS]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    w = 0.36
    ax.bar([i - w / 2 for i in x], [r[1] for r in RUNS], w, label="signal-style prompt", color="#B0B0B0")
    ax.bar([i + w / 2 for i in x], [r[2] for r in RUNS], w, label="grounding-tightened", color="#54A24B")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_ylabel("score"); ax.set_ylim(0, 1.0)
    ax.set_title("Grounding prompt: hallucination halved, faithfulness up",
                 fontsize=12, weight="bold")
    for i, r in enumerate(RUNS):
        ax.text(i - w / 2, r[1], f"{r[1]:.2f}", ha="center", va="bottom", fontsize=8)
        ax.text(i + w / 2, r[2], f"{r[2]:.2f}", ha="center", va="bottom", fontsize=8)
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "before_after.png", dpi=130); plt.close(fig)


# Per-description claim accounting, after the fix.
CLAIMS = [("grounded", 19.8), ("unsupported", 1.0)]


def claims() -> None:
    fig, ax = plt.subplots(figsize=(5.5, 4.4))
    labels = [c[0] for c in CLAIMS]
    bars = ax.bar(labels, [c[1] for c in CLAIMS], color=["#54A24B", "#E45756"])
    ax.set_ylabel("avg claims per description")
    ax.set_title("~1 of ~21 claims unsupported (after fix)", fontsize=12, weight="bold")
    for b, c in zip(bars, CLAIMS):
        ax.text(b.get_x() + b.get_width() / 2, c[1], f"{c[1]:.1f}", ha="center", va="bottom", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "claims.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    _OUT.mkdir(parents=True, exist_ok=True)
    before_after(); claims()
    print(f"wrote charts to {_OUT}/")
