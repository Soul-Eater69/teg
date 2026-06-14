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
    ("raw@7k retrieval", "raw@7k", "raw@3k", "raw@7k", 0.742, 23, 6.6, 0.840),
]
_WINNER = "raw + summary"

# New-ticket prompt budget (summary retrieval + summary historic; only the new ticket's raw cap
# changes): the full ~24k raw beats a 7k cap - the extra context helps the LLM decide.
PROMPT_BUDGET = [("raw @7k", 0.759, 26), ("raw @24k (full)", 0.780, 31)]

# Latency split (retrieval vs the LLM-selection call) - retrieval is sub-second; the LLM call is
# the whole cost and it tracks the historic block size.
LATENCY_SPLIT = [
    ("winner\n(summary historic)", 0.38, 3.7),
    ("raw@3k historic", 0.79, 5.8),
]


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


def prompt_budget() -> None:
    labels = [r[0] for r in PROMPT_BUDGET]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    _bar(ax, labels, [r[1] for r in PROMPT_BUDGET], "micro F1",
         "New-ticket prompt: full raw beats a 7k cap", highlight="raw @24k (full)")
    ax.set_ylim(0.74, 0.79)
    fig.tight_layout(); fig.savefig(_OUT / "prompt_budget.png", dpi=130); plt.close(fig)


def latency_split() -> None:
    labels = [r[0] for r in LATENCY_SPLIT]
    retr = [r[1] for r in LATENCY_SPLIT]
    llm = [r[2] for r in LATENCY_SPLIT]
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    x = range(len(labels))
    ax.bar(x, retr, label="retrieval", color="#54A24B")
    ax.bar(x, llm, bottom=retr, label="LLM selection", color="#4C78A8")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("seconds"); ax.set_title("Where the time goes (retrieval vs LLM)",
                                           fontsize=12, weight="bold")
    for i, (r, l) in enumerate(zip(retr, llm)):
        ax.text(i, r + l, f"{r + l:.1f}s", ha="center", va="bottom", fontsize=9)
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "latency_split.png", dpi=130); plt.close(fig)


# Count mode -> precision / recall / F1 (winner config, 100 gt>=3 tickets). The LLM follows the
# requested count exactly (100% followed, 0% padded), so the count is a precision<->recall dial.
COUNT_MODE = [
    ("count = gt", 0.786, 0.786, 0.786),
    ("gt + 2", 0.638, 0.854, 0.730),
    ("fixed 10", 0.497, 0.842, 0.625),
]

# Why the LLM dropped GT it saw (avg of the gt+2 and fixed-10 explain-drops runs).
DROP_REASONS = [
    ("lower_priority\n(count cut it)", 74),
    ("off_topic\n(disagrees)", 17),
    ("near_duplicate\n(twin picked)", 9),
]


def count_mode() -> None:
    labels = [r[0] for r in COUNT_MODE]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(7, 4.4))
    w = 0.27
    ax.bar([i - w for i in x], [r[1] for r in COUNT_MODE], w, label="precision", color="#E45756")
    ax.bar([i for i in x], [r[2] for r in COUNT_MODE], w, label="recall", color="#54A24B")
    ax.bar([i + w for i in x], [r[3] for r in COUNT_MODE], w, label="F1", color="#4C78A8")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_ylabel("score"); ax.set_ylim(0.4, 0.9)
    ax.set_title("Count is a precision<->recall dial (LLM obeys it exactly)",
                 fontsize=12, weight="bold")
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(_OUT / "count_mode.png", dpi=130); plt.close(fig)


def drop_reasons() -> None:
    labels = [r[0] for r in DROP_REASONS]
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    _bar(ax, labels, [r[1] for r in DROP_REASONS], "% of dropped GT",
         "Why the LLM skips GT it saw", fmt="{:.0f}%", highlight=labels[0], color="#72B7B2")
    fig.tight_layout(); fig.savefig(_OUT / "drop_reasons.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    _OUT.mkdir(parents=True, exist_ok=True)
    f1_ladder(); retrieval_compare(); latency(); prompt_budget(); latency_split()
    count_mode(); drop_reasons()
    print(f"wrote charts to {_OUT}/")
