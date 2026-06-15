"""Charts for the L3 capability EDA (docs/l3_capability_eda.md).

Measured snapshots from the L3 runs (25-ticket sample, seed 13; ~231 scored VS). Hardcoded - an
analysis artifact. Writes PNGs to docs/l3_charts/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_OUT = Path("docs/l3_charts")


def _bar(ax, labels, values, ylabel, title, fmt="{:.3f}", highlight=None, color="#4C78A8"):
    colors = ["#E45756" if highlight and l == highlight else color for l in labels]
    bars = ax.bar(range(len(labels)), values, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel(ylabel); ax.set_title(title, fontsize=12, weight="bold")
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v, fmt.format(v), ha="center", va="bottom", fontsize=8)
    ax.grid(axis="y", alpha=0.3)


# one_call across the three prompt versions: strict -> lean -> no-count-cap.
JOURNEY = [
    ("recall", [0.486, 0.691, 0.867]),
    ("precision", [0.513, 0.526, 0.476]),
    ("F1", [0.499, 0.597, 0.615]),
]
_STAGES = ["strict", "lean", "no count cap"]
_COLORS = ["#B0B0B0", "#9ECAE1", "#54A24B"]


def journey() -> None:
    fig, ax = plt.subplots(figsize=(8, 4.6))
    metrics = [m for m, _ in JOURNEY]
    x = range(len(metrics))
    w = 0.26
    for i, label in enumerate(_STAGES):
        vals = [vals[i] for _, vals in JOURNEY]
        bars = ax.bar([p + (i - 1) * w for p in x], vals, w, label=label, color=_COLORS[i])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(list(x)); ax.set_xticklabels(metrics)
    ax.set_ylabel("score"); ax.set_ylim(0, 1.0)
    ax.set_title("Removing the count cap recovered recall (precision the trade)",
                 fontsize=12, weight="bold")
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "journey.png", dpi=130); plt.close(fig)


# Drop grounding after the recall fix (127 dropped answerable GT L3).
GROUNDING = [
    ("no_context\n(convention noise)", 50), ("context_present\n_but_dropped", 28), ("weak_broad", 22),
]


def grounding() -> None:
    labels = [r[0] for r in GROUNDING]
    fig, ax = plt.subplots(figsize=(6.5, 4.4))
    _bar(ax, labels, [r[1] for r in GROUNDING], "% of dropped L3",
         "What's left: half is BA convention (not card-derivable)", fmt="{:.0f}%",
         highlight=labels[0], color="#72B7B2")
    fig.tight_layout(); fig.savefig(_OUT / "grounding.png", dpi=130); plt.close(fig)


# Interlink: prompt isolation + salvage -> 0.
MISLINK = [("first run", 6.1), ("isolation +\nsalvage", 0.0)]


def mislink() -> None:
    labels = [r[0] for r in MISLINK]
    fig, ax = plt.subplots(figsize=(5, 4.2))
    _bar(ax, labels, [r[1] for r in MISLINK], "cross-stage mislink %",
         "Interlink solved (prevent + salvage)", fmt="{:.1f}%", highlight="isolation +\nsalvage",
         color="#54A24B")
    fig.tight_layout(); fig.savefig(_OUT / "mislink.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    _OUT.mkdir(parents=True, exist_ok=True)
    journey(); grounding(); mislink()
    print(f"wrote charts to {_OUT}/")
