"""Charts for the attachment-cap x token-budget optimization (from token_budget_grid.py, 374 tickets).

    uv run python scripts/build_token_budget_report.py   ->  charts in docs/token_charts/
"""

from __future__ import annotations

from pathlib import Path

CHARTS = Path("docs/token_charts")
BUDGETS = [4, 6, 8, 12, 16, 24, 32]  # k tokens
COVERAGE = {  # cap -> coverage % at each budget
    "1": [63, 74, 81, 88, 95, 98, 99],
    "3": [51, 62, 70, 80, 88, 95, 98],
    "4": [51, 61, 68, 78, 86, 95, 98],
    "all": [51, 61, 68, 78, 86, 94, 97],
}
CONTENT_KEPT = {"1": 77, "2": 92, "3": 97, "4": 99, "5": 100, "all": 100}


def build() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHARTS.mkdir(parents=True, exist_ok=True)
    GREEN, AMBER, BLUE, RED, GREY = "#2a9d4a", "#e8a23d", "#3d7fe8", "#c0392b", "#9aa0a6"

    def save(fig, name):
        fig.savefig(CHARTS / f"{name}.png", dpi=150, bbox_inches="tight"); plt.close(fig)

    # 1. coverage vs budget, one line per cap
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    styles = {"1": (RED, "-o"), "3": (AMBER, "-s"), "4": (GREEN, "-^"), "all": (GREY, "--D")}
    for cap, vals in COVERAGE.items():
        c, st = styles[cap]
        ax.plot(BUDGETS, vals, st, color=c, label=f"keep {cap} attachments")
    ax.axhline(95, color="#888", ls=":", lw=1); ax.text(4.2, 95.6, "95% of tickets", fontsize=8, color="#666")
    ax.set_xticks(BUDGETS); ax.set_xlabel("token budget (k)"); ax.set_ylabel("% of tickets that fit (no truncation)")
    ax.set_ylim(45, 102); ax.figure.suptitle("Token budget is the real lever — the attachment cap barely moves it",
                                              fontsize=13, fontweight="bold")
    ax.set_title("The lines sit close together: capping attachments hardly changes coverage (most tickets are small).",
                 fontsize=9, style="italic", color="#555")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    save(fig, "coverage_curves")

    # 2. content kept by cap
    fig, ax = plt.subplots(figsize=(7.5, 4))
    keys = list(CONTENT_KEPT); vals = list(CONTENT_KEPT.values())
    colors = [RED, AMBER, GREEN, GREEN, GREEN, GREY]
    bars = ax.bar(keys, vals, color=colors[:len(keys)])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylim(0, 110); ax.set_xlabel("attachments kept"); ax.set_ylabel("% of attachment content kept")
    ax.figure.suptitle("Keeping 3–4 attachments retains ~all the content", fontsize=14, fontweight="bold")
    ax.set_title("The 5th+ attachment adds under 3% of content — safe to drop the tail.", fontsize=10, style="italic", color="#555")
    save(fig, "content_kept")

    print(f"charts -> {CHARTS}")


if __name__ == "__main__":
    build()
