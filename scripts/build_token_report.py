"""Charts for the token/attachment findings (Tasks 4 & 5). Real numbers from the 374-ticket run.

    uv run python scripts/build_token_report.py   ->  charts in docs/token_charts/
"""

from __future__ import annotations

from pathlib import Path

CHARTS = Path("docs/token_charts")

# from out/eda/token_analysis.json (374 tickets)
N = 374
RAW = {"median": 3854, "p90": 19433, "p95": 25921, "max": 88614}
BUDGET = {"4,000": 184, "8,000": 120, "16,000": 53}
ATT_COUNT = {"0": 67, "1": 93, "2": 66, "3": 56, "4": 54, "5": 22, "6+": 16}
FILE_TYPES = {"PowerPoint": 410, "PDF": 277, "Word": 153}
# avg raw tokens by attachment count (and ticket counts); 6+ grouped (small samples)
TOKENS_BY_COUNT = {"0": 552, "1": 3042, "2": 6708, "3": 9489, "4": 11652, "5": 26520, "6+": 21770}
TICKETS_BY_COUNT = {"0": 67, "1": 93, "2": 66, "3": 56, "4": 54, "5": 22, "6+": 16}


def build() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHARTS.mkdir(parents=True, exist_ok=True)
    GREEN, AMBER, BLUE, RED = "#2a9d4a", "#e8a23d", "#3d7fe8", "#c0392b"

    def save(fig, name):
        fig.savefig(CHARTS / f"{name}.png", dpi=150, bbox_inches="tight"); plt.close(fig)

    def label(ax, bars, vals, fmt="{:,}"):
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(v),
                    ha="center", va="bottom", fontsize=9, fontweight="bold")

    # 1. how big is a ticket's text (raw tokens) - median/p90/p95/max with the 40k guardrail line
    fig, ax = plt.subplots(figsize=(7.5, 4))
    keys = ["Typical\n(median)", "Big\n(top 10%)", "Bigger\n(top 5%)", "Largest\n(max)"]
    vals = [RAW["median"], RAW["p90"], RAW["p95"], RAW["max"]]
    bars = ax.bar(keys, vals, color=[GREEN, BLUE, AMBER, RED])
    label(ax, bars, vals)
    ax.set_ylabel("tokens in the raw text"); ax.figure.suptitle("How big is a ticket's text?", fontsize=14, fontweight="bold")
    ax.set_title("Most tickets are small (median ~3.9k tokens); a few are huge (max ~89k).", fontsize=10, style="italic", color="#555")
    save(fig, "size")

    # 2. tickets over each budget
    fig, ax = plt.subplots(figsize=(7.5, 4))
    keys = list(BUDGET); vals = list(BUDGET.values())
    bars = ax.bar([f"> {k}\ntokens" for k in keys], vals, color=[AMBER, BLUE, GREEN])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v} ({v/N:.0%})", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("number of tickets"); ax.figure.suptitle("How many tickets need more than each budget?", fontsize=14, fontweight="bold")
    ax.set_title("About half need >4k tokens; only 14% need more than 16k.", fontsize=10, style="italic", color="#555")
    save(fig, "budget")

    # 3. attachments per ticket
    fig, ax = plt.subplots(figsize=(7.5, 4))
    keys = list(ATT_COUNT); vals = list(ATT_COUNT.values())
    colors = [RED] + [GREEN] * 4 + [AMBER, AMBER]
    bars = ax.bar(keys, vals, color=colors[:len(keys)])
    label(ax, bars, vals)
    ax.set_xlabel("attachments on the ticket"); ax.set_ylabel("number of tickets")
    ax.figure.suptitle("How many attachments does a ticket have?", fontsize=14, fontweight="bold")
    ax.set_title("18% have none; most have 1-4 (so the top-4 rule keeps everything for 90%).", fontsize=10, style="italic", color="#555")
    save(fig, "attachments")

    # 4. file types
    fig, ax = plt.subplots(figsize=(7.5, 4))
    keys = list(FILE_TYPES); vals = list(FILE_TYPES.values()); tot = sum(vals)
    bars = ax.bar(keys, vals, color=[AMBER, RED, BLUE])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v} ({v/tot:.0%})", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("number of attachments"); ax.figure.suptitle("What kinds of attachments are they?", fontsize=14, fontweight="bold")
    ax.set_title("PowerPoint is the most common, then PDF, then Word.", fontsize=10, style="italic", color="#555")
    save(fig, "filetypes")

    # 5. avg tokens by attachment count (the lever connecting count -> token budget)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    keys = list(TOKENS_BY_COUNT); vals = list(TOKENS_BY_COUNT.values())
    colors = [GREEN] * 5 + [RED, AMBER]
    bars = ax.bar(keys, vals, color=colors[:len(keys)])
    for b, v, k in zip(bars, vals, keys):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:,}\n({TICKETS_BY_COUNT[k]})",
                ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax.axhline(40000, color=RED, ls="--", lw=1.2); ax.set_ylim(0, 45000)
    ax.set_xlabel("attachments on the ticket (ticket count in parentheses)"); ax.set_ylabel("avg tokens")
    ax.figure.suptitle("More attachments → more tokens (and a jump at 5)", fontsize=14, fontweight="bold")
    ax.set_title("~3k tokens per attachment up to 4 (~12k); 5-attachment tickets jump to ~27k.", fontsize=10, style="italic", color="#555")
    save(fig, "tokens_by_count")

    print(f"charts -> {CHARTS}")


if __name__ == "__main__":
    build()
