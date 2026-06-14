"""Charts for the stage-selection EDA (docs/stage_selection_eda.md).

Measured snapshots from the stage runs (50-ticket gt>=3 cohort + full population). Hardcoded on
purpose - an analysis artifact, not a live recompute. Writes PNGs to docs/stage_charts/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_OUT = Path("docs/stage_charts")


def _bar(ax, labels, values, ylabel, title, fmt="{:.3f}", highlight=None, color="#4C78A8"):
    colors = ["#E45756" if highlight and l == highlight else color for l in labels]
    bars = ax.bar(range(len(labels)), values, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12, weight="bold")
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v, fmt.format(v), ha="center", va="bottom", fontsize=8)
    ax.grid(axis="y", alpha=0.3)


# input x mode F1 (402 pairs, before prune). summary wins; one_call calibrated.
INPUT_MODE = [
    ("summary\nper_vs", 0.446), ("summary\none_call", 0.439),
    ("raw\nper_vs", 0.426), ("raw\none_call", 0.415),
]


def input_mode() -> None:
    labels = [r[0] for r in INPUT_MODE]
    fig, ax = plt.subplots(figsize=(7, 4.4))
    _bar(ax, labels, [r[1] for r in INPUT_MODE], "micro F1",
         "Input x mode (summary beats raw; one_call calibrated)", highlight="summary\none_call")
    ax.set_ylim(0.39, 0.46)
    fig.tight_layout(); fig.savefig(_OUT / "input_mode.png", dpi=130); plt.close(fig)


# The coverage fix: pruning uncatalogued GT stages lifts recall/F1 (raw/one_call).
PRUNE = [("recall", 0.432, 0.544), ("F1", 0.424, 0.476)]


def prune_lift() -> None:
    labels = [r[0] for r in PRUNE]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(6, 4.4))
    w = 0.35
    ax.bar([i - w / 2 for i in x], [r[1] for r in PRUNE], w, label="before prune", color="#B0B0B0")
    ax.bar([i + w / 2 for i in x], [r[2] for r in PRUNE], w, label="after prune", color="#54A24B")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_ylabel("score"); ax.set_ylim(0.3, 0.6)
    ax.set_title("Pruning uncatalogued GT lifts the fair numbers", fontsize=12, weight="bold")
    for i, r in enumerate(PRUNE):
        ax.text(i - w / 2, r[1], f"{r[1]:.3f}", ha="center", va="bottom", fontsize=8)
        ax.text(i + w / 2, r[2], f"{r[2]:.3f}", ha="center", va="bottom", fontsize=8)
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "prune_lift.png", dpi=130); plt.close(fig)


# FN breakdown BEFORE prune (% of all FN): coverage was the biggest.
FN_BREAKDOWN = [
    ("stage not in\ncatalogue", 42), ("no ticket\nevidence", 24),
    ("present but\ndropped", 21), ("weak/broad", 13),
]


def fn_breakdown() -> None:
    labels = [r[0] for r in FN_BREAKDOWN]
    fig, ax = plt.subplots(figsize=(7, 4.4))
    _bar(ax, labels, [r[1] for r in FN_BREAKDOWN], "% of all FN",
         "Why FN happened (before prune): mostly NOT the model", fmt="{:.0f}%",
         highlight="stage not in\ncatalogue", color="#72B7B2")
    fig.tight_layout(); fig.savefig(_OUT / "fn_breakdown.png", dpi=130); plt.close(fig)


# Drop grounding AFTER prune (answerable stages only).
GROUNDING = [
    ("no_context\n(label noise)", 41), ("present_but\n_dropped", 40), ("weak_broad", 20),
]


def grounding() -> None:
    labels = [r[0] for r in GROUNDING]
    fig, ax = plt.subplots(figsize=(6.5, 4.4))
    _bar(ax, labels, [r[1] for r in GROUNDING], "% of dropped stages",
         "Drops on answerable stages: 41% have no evidence", fmt="{:.0f}%", color="#72B7B2")
    fig.tight_layout(); fig.savefig(_OUT / "grounding.png", dpi=130); plt.close(fig)


# Swap reasons after prune - raw counts (n=264) so the bars are exact, not rounded to 101%.
SWAP = [
    ("picks_more\n_specific", 94), ("no_evidence\n_for_dropped", 69), ("dropped_too\n_broad", 63),
    ("adjacent_stage\n_confusion", 28), ("genuine\nmiss", 10),
]
_SWAP_N = sum(v for _, v in SWAP)


def swap() -> None:
    labels = [r[0] for r in SWAP]
    pct = [100 * v / _SWAP_N for _, v in SWAP]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    _bar(ax, labels, pct, "% of drops",
         f"Why the picks beat each dropped stage (n={_SWAP_N})", fmt="{:.0f}%",
         highlight="genuine\nmiss", color="#4C78A8")
    fig.tight_layout(); fig.savefig(_OUT / "swap.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    _OUT.mkdir(parents=True, exist_ok=True)
    input_mode(); prune_lift(); fn_breakdown(); grounding(); swap()
    print(f"wrote charts to {_OUT}/")
