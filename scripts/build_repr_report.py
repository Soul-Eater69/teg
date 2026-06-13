"""Charts for the retrieval-representation EDA (raw vs summary vs chunking).

    uv run python scripts/build_repr_report.py   ->  charts in docs/repr_charts/
"""

from __future__ import annotations

from pathlib import Path

CHARTS = Path("docs/repr_charts")
# content kept if we truncate every ticket's raw text at a budget (for the embedding)
TRUNC = {"5k": 41, "7k": 51, "7.5k": 54, "10k": 63, "15k": 77}
TICKETS_FULL = {"5k": 56, "7k": 66, "7.5k": 67, "10k": 74, "15k": 84}
# per-attachment text size (tokens) - chunk size if we chunk by attachment
ATT_TOKEN_DIST = {"0-1k": 290, "1-2k": 204, "2-4k": 176, "4-8k": 95, "8-16k": 58, "16k+": 17}


def build() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHARTS.mkdir(parents=True, exist_ok=True)
    GREEN, AMBER, BLUE, RED = "#2a9d4a", "#e8a23d", "#3d7fe8", "#c0392b"

    def save(fig, name):
        fig.savefig(CHARTS / f"{name}.png", dpi=150, bbox_inches="tight"); plt.close(fig)

    # 1. content lost to truncation (the case AGAINST raw-truncated embedding)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ks = list(TRUNC)
    ax.plot(ks, list(TRUNC.values()), "-o", color=RED, label="% of all content embedded")
    ax.plot(ks, list(TICKETS_FULL.values()), "-s", color=BLUE, label="% of tickets fully captured")
    for k, v in TRUNC.items():
        ax.annotate(f"{v}%", (k, v), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=8, color=RED)
    ax.axhline(100, color="#888", ls=":", lw=1)
    ax.set_ylim(0, 110); ax.set_xlabel("truncate raw text at"); ax.set_ylabel("%")
    ax.figure.suptitle("Truncating raw text for the embedding loses a LOT of content", fontsize=13, fontweight="bold")
    ax.set_title("At a 7k embedding cap only 51% of content is embedded - the big tickets hold most of it.",
                 fontsize=9, style="italic", color="#555")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    save(fig, "truncation_loss")

    # 2. chunk size = per-attachment tokens; most fit one embedding vector
    fig, ax = plt.subplots(figsize=(7.5, 4))
    colors = [GREEN, GREEN, GREEN, GREEN, AMBER, RED]
    bars = ax.bar(list(ATT_TOKEN_DIST), list(ATT_TOKEN_DIST.values()), color=colors)
    for b, v in zip(bars, ATT_TOKEN_DIST.values()):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.axvline(3.5, color=RED, ls="--", lw=1.2); ax.text(3.6, 250, "~7.5k embed limit", color=RED, fontsize=8)
    ax.set_xlabel("tokens in one attachment (= one chunk)"); ax.set_ylabel("number of attachments")
    ax.figure.suptitle("If we chunk by attachment, 91% fit one embedding vector", fontsize=13, fontweight="bold")
    ax.set_title("765 of 840 attachments are under the embedding limit; only ~75 (9%) need sub-chunking.",
                 fontsize=9, style="italic", color="#555")
    save(fig, "chunk_size")

    print(f"charts -> {CHARTS}")


if __name__ == "__main__":
    build()
