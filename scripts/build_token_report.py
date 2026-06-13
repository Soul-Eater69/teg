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
# distributions (histograms) from the full EDA run
TEXT_DIST = {"0-2k": 142, "2-4k": 48, "4-8k": 64, "8-16k": 67, "16-32k": 42, "32k+": 11}
ATT_TOKEN_DIST = {"0-1k": 290, "1-2k": 204, "2-4k": 176, "4-8k": 95, "8-16k": 58, "16k+": 17}
ATT_BYTE_DIST = {"<100KB": 145, "100-500KB": 263, "0.5-1MB": 92, "1-2MB": 114, "2-5MB": 134, "5MB+": 92}
# per file type: count, avg tokens/file, text density (tokens per MB)
TYPE_DETAIL = {"PowerPoint": {"count": 410, "avg_tokens": 2158, "tok_per_mb": 893, "avg_mb": 2.42},
               "PDF": {"count": 277, "avg_tokens": 5908, "tok_per_mb": 5091, "avg_mb": 1.16},
               "Word": {"count": 153, "avg_tokens": 1051, "tok_per_mb": 2243, "avg_mb": 0.47}}
HEALTH = {"Carry text": 840, "Images / unsupported": 726, "Empty": 13}  # of 1,579 attachments
# % of tickets whose full raw text (description + all attachments) fits under each budget
BUDGET_FIT = {"5k": 56, "10k": 74, "15k": 84, "20k": 91, "25k": 95, "30k": 97}


def build() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHARTS.mkdir(parents=True, exist_ok=True)
    GREEN, AMBER, BLUE, RED, GREY = "#2a9d4a", "#e8a23d", "#3d7fe8", "#c0392b", "#9aa0a6"

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

    # 6. distribution of combined text size per ticket
    fig, ax = plt.subplots(figsize=(7.5, 4))
    bars = ax.bar(list(TEXT_DIST), list(TEXT_DIST.values()), color=[GREEN, GREEN, BLUE, BLUE, AMBER, RED])
    label(ax, bars, list(TEXT_DIST.values()), "{}")
    ax.set_xlabel("tokens in a ticket's full text"); ax.set_ylabel("number of tickets")
    ax.figure.suptitle("Most tickets' text is small; a long tail is large", fontsize=14, fontweight="bold")
    ax.set_title("142 of 374 tickets are under 2k tokens; 53 are over 16k.", fontsize=10, style="italic", color="#555")
    save(fig, "text_dist")

    # 7. distribution of per-attachment text size (tokens)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    bars = ax.bar(list(ATT_TOKEN_DIST), list(ATT_TOKEN_DIST.values()), color=[GREEN, GREEN, BLUE, BLUE, AMBER, RED])
    label(ax, bars, list(ATT_TOKEN_DIST.values()), "{}")
    ax.set_xlabel("tokens in one attachment"); ax.set_ylabel("number of attachments")
    ax.figure.suptitle("How big is each attachment (text)?", fontsize=14, fontweight="bold")
    ax.set_title("Most attachments are small (under 2k tokens); 75 are over 8k.", fontsize=10, style="italic", color="#555")
    save(fig, "att_token_dist")

    # 8. distribution of per-attachment file size (bytes)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    bars = ax.bar(list(ATT_BYTE_DIST), list(ATT_BYTE_DIST.values()), color=[GREEN, GREEN, BLUE, AMBER, AMBER, RED])
    label(ax, bars, list(ATT_BYTE_DIST.values()), "{}")
    ax.set_xlabel("file size of one attachment"); ax.set_ylabel("number of attachments")
    ax.figure.suptitle("How big is each attachment (on disk)?", fontsize=14, fontweight="bold")
    ax.set_title("Many are small, but 226 attachments are over 2 MB (the decks).", fontsize=10, style="italic", color="#555")
    save(fig, "att_byte_dist")

    # 9. file type: common vs text-rich vs dense
    import numpy as np
    fig, ax = plt.subplots(figsize=(8, 4.2))
    types = list(TYPE_DETAIL); x = np.arange(len(types)); w = 0.38
    counts = [TYPE_DETAIL[t]["count"] for t in types]
    avg_tok = [TYPE_DETAIL[t]["avg_tokens"] for t in types]
    ax2 = ax.twinx()
    b1 = ax.bar(x - w / 2, counts, w, color=BLUE, label="how many (count)")
    b2 = ax2.bar(x + w / 2, avg_tok, w, color=GREEN, label="avg text per file (tokens)")
    for b, v in zip(b1, counts): ax.text(b.get_x() + b.get_width()/2, v, f"{v}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    for b, v in zip(b2, avg_tok): ax2.text(b.get_x() + b.get_width()/2, v, f"{v:,}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(types); ax.set_ylabel("count (blue)"); ax2.set_ylabel("avg tokens/file (green)")
    ax.figure.suptitle("PowerPoint is most common, but PDF carries the most text", fontsize=13, fontweight="bold")
    ax.set_title("PowerPoint: 410 files, only ~2.2k tokens each (893 tok/MB). PDF: ~5.9k tokens each (5,091 tok/MB).",
                 fontsize=9, style="italic", color="#555")
    ax.legend(loc="upper left", fontsize=8); ax2.legend(loc="upper right", fontsize=8)
    save(fig, "file_type_text")

    # 10. extraction health
    fig, ax = plt.subplots(figsize=(7.5, 4))
    bars = ax.bar(list(HEALTH), list(HEALTH.values()), color=[GREEN, GREY, RED])
    tot = sum(HEALTH.values())
    for b, v in zip(bars, HEALTH.values()):
        ax.text(b.get_x() + b.get_width()/2, v, f"{v} ({v/tot:.0%})", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("number of attachments"); ax.figure.suptitle("Only half of attachments carry text", fontsize=14, fontweight="bold")
    ax.set_title("Of 1,579 attachments, 840 (53%) have text; ~46% are images/unsupported.", fontsize=10, style="italic", color="#555")
    save(fig, "extraction_health")

    # 11. tokens per ticket vs budget — % of tickets that fit
    fig, ax = plt.subplots(figsize=(7.5, 4))
    keys = list(BUDGET_FIT); vals = list(BUDGET_FIT.values())
    colors = [RED, AMBER, AMBER, BLUE, GREEN, GREEN]
    bars = ax.bar([f"{k}\ntokens" for k in keys], vals, color=colors[:len(keys)])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylim(0, 105); ax.set_ylabel("% of tickets whose full text fits")
    ax.figure.suptitle("What token budget fits most tickets?", fontsize=14, fontweight="bold")
    ax.set_title("Raw text (description + all attachments). 20k fits 91%; 25k fits 95%.", fontsize=10, style="italic", color="#555")
    save(fig, "budget_fit")

    print(f"charts -> {CHARTS}")


if __name__ == "__main__":
    build()
