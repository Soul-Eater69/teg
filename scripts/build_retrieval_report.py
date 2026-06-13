"""Authored, charted retrieval-COVERAGE report (docx) - plain language, real charts.

Scope: how well the "similar past tickets" search COVERS a ticket's correct Value Streams. Numbers
from the 373-ticket historic-lane run (see DATA). One command, no flags:

    uv sync --extra eda --extra extract
    uv run python scripts/build_retrieval_report.py   ->  out/eval/retrieval_report.docx
"""

from __future__ import annotations

from pathlib import Path

OUT = Path("out/eval/retrieval_report.docx")

# ---- real numbers from the 373-ticket run ----------------------------------------------------
DATA = {
    "n": 373,
    "k": [6, 8, 10],
    "recall": [0.902, 0.925, 0.944],          # avg fraction of a ticket's GT covered
    "hit": [0.960, 0.968, 0.976],             # % of tickets that found >=1
    "fully_covered": [0.780, 0.812, 0.850],   # % of tickets that found ALL
    # single vs multi coverage at K=6
    "cov_single": 0.922, "cov_multi": 0.880,
    "full_single": 0.922, "full_multi": 0.628,
    "single_n": 193, "multi_n": 180,
    "gt_buckets": {"Just 1": 193, "2-4": 98, "5-9": 54, "10+": 28},
    "first_rank": {"1": 288, "2": 36, "3": 20, "4-10": 20, "none": 9},
}


def _save(fig, plt, charts, name):
    p = charts / f"{name}.png"
    fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig)
    return str(p)


def _bars(ax, labels, values, colors=None, pct=True):
    bars = ax.bar(labels, values, color=colors)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.0%}" if pct else f"{v:,}",
                ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)


def build() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from docx import Document
    from docx.shared import Inches

    d = DATA
    charts = OUT.parent / "retrieval_report_charts"
    charts.mkdir(parents=True, exist_ok=True)
    GREEN, AMBER, BLUE, RED = "#2a9d4a", "#e8a23d", "#3d7fe8", "#c0392b"

    # 1. what happened to each ticket - mutually exclusive, sums to 100%
    full, some, none = d["fully_covered"][0], d["hit"][0] - d["fully_covered"][0], 1 - d["hit"][0]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    _bars(ax, ["Found ALL their\nValue Streams", "Found SOME\n(missed a few)", "Found NONE"],
          [full, some, none], colors=[GREEN, AMBER, RED])
    ax.set_ylim(0, 1.0); ax.figure.suptitle("What happened to each ticket? (showing 6 examples)", fontsize=14, fontweight="bold")
    ax.set_title("Every ticket is in exactly one group — the three add up to 100%.", fontsize=10, style="italic", color="#555")
    c1 = _save(fig, plt, charts, "coverage")

    # 2. GT size distribution
    fig, ax = plt.subplots(figsize=(7.5, 4))
    _bars(ax, list(d["gt_buckets"]), list(d["gt_buckets"].values()), colors=[GREEN, BLUE, AMBER, RED], pct=False)
    ax.figure.suptitle("How many Value Streams does a ticket have?", fontsize=14, fontweight="bold")
    ax.set_title("Half the tickets have just one (easy); a tail have up to 19 (hard).", fontsize=10, style="italic", color="#555")
    c2 = _save(fig, plt, charts, "gt_dist")

    # 3. easy vs hard coverage
    fig, ax = plt.subplots(figsize=(7.5, 4))
    x = np.arange(2); w = 0.35
    b1 = ax.bar(x - w / 2, [d["cov_single"], d["cov_multi"]], w, label="Found MOST streams (avg)", color=BLUE)
    b2 = ax.bar(x + w / 2, [d["full_single"], d["full_multi"]], w, label="Found EVERY stream", color=GREEN)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{b.get_height():.0%}",
                    ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels([f"Easy\n(1 stream, {d['single_n']})", f"Hard\n(2+, {d['multi_n']})"])
    ax.set_ylim(0, 1.1); ax.figure.suptitle("Hard tickets: we find most, but rarely all", fontsize=14, fontweight="bold")
    ax.set_title("On hard tickets, avg coverage is 88% but full coverage drops to 63%.", fontsize=10, style="italic", color="#555")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
    c3 = _save(fig, plt, charts, "easy_hard")

    # 4. coverage across K (coverage-only)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(d["k"], d["recall"], "-o", color=GREEN, label="Avg coverage")
    ax.plot(d["k"], d["fully_covered"], "-s", color=BLUE, label="Found everything")
    for kk, r, f in zip(d["k"], d["recall"], d["fully_covered"]):
        ax.annotate(f"{r:.0%}", (kk, r), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
        ax.annotate(f"{f:.0%}", (kk, f), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=8)
    ax.set_xticks(d["k"]); ax.set_xlabel("Number of past tickets shown"); ax.set_ylim(0.6, 1.0)
    ax.figure.suptitle("Showing more tickets barely improves coverage", fontsize=14, fontweight="bold")
    ax.set_title("Going 6 → 10 adds only ~4 points — diminishing returns. 6 is enough.", fontsize=10, style="italic", color="#555")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    c4 = _save(fig, plt, charts, "tradeoff")

    # 5. first correct stream rank
    fig, ax = plt.subplots(figsize=(7.5, 4))
    fr = d["first_rank"]
    _bars(ax, list(fr), list(fr.values()), colors=[GREEN, BLUE, BLUE, BLUE, RED], pct=False)
    ax.figure.suptitle("Where the first correct Value Stream appears", fontsize=14, fontweight="bold")
    ax.set_title("For 288 of 373 tickets the very first result already carries a correct stream.", fontsize=10, style="italic", color="#555")
    ax.set_xlabel("position in the list")
    c5 = _save(fig, plt, charts, "first_rank")

    # ---------------- document
    doc = Document()
    doc.add_heading("How much of the answer does our “similar past tickets” search find?", level=0)
    doc.add_paragraph(
        "A plain-language report on the search that finds similar past tickets and shows them to the "
        "model. We measure COVERAGE: of a ticket's correct Value Streams, how many does the search "
        "surface. Tested on 373 real tickets. Each chart says what it shows and how to read it.")

    doc.add_heading("Bottom line", level=1)
    for b in [
        "The search reliably finds the right Value Streams. The correct ones show up for 90% of a "
        "typical ticket's streams, and 96% of tickets find at least one.",
        "78% of tickets find EVERY one of their correct Value Streams; 18% find some but miss a few; "
        "only 4% find none.",
        "On average a ticket has 3.2 correct Value Streams and the search finds ~2.9 of them (90%).",
        "The misses are concentrated in the HARD tickets (those with several Value Streams) — there we "
        "find most streams (88%) but the complete set only 63% of the time.",
        "Showing 6 past tickets is enough — going to 10 adds only ~4 points of coverage.",
        "Bottom line: the search puts the right answers in front of the model — coverage is not the "
        "bottleneck.",
    ]:
        doc.add_paragraph(b, style="List Bullet")

    sections = [
        ("1. What happened to each ticket", c1,
         "When we show the 6 most similar past tickets, every ticket lands in exactly one of three "
         "groups (so they add up to 100%): found ALL its correct Value Streams (78%), found SOME but "
         "missed a few (18%), or found NONE (4%). So 96% find at least one and 78% find everything.\n\n"
         "One more number, measured differently: averaged across tickets, a typical ticket has 90% of "
         "its correct streams present in the examples. (That 90% is a per-ticket average, not a count of "
         "tickets — both say coverage is strong.)"),
        ("2. Not every ticket is equally hard", c2,
         "Each bar is how many of the 373 tickets have that many correct Value Streams. Half (193) have "
         "just one — easy, one answer to find. The rest have several, and 28 tickets have 10 or more (a "
         "few have 19). The more streams a ticket has, the harder it is to find them all — so the "
         "coverage numbers are an average across easy and hard tickets."),
        ("3. Hard tickets: we find most, but rarely all", c3,
         "Two ticket groups (easy = 1 stream, 193 tickets; hard = 2+, 180 tickets), each measured two "
         "ways. BLUE 'found most' is the average fraction of a ticket's streams found — easy 92%, hard "
         "88%. GREEN 'found every' is how often ALL streams were found — easy 92%, hard only 63%.\n\n"
         "In plain counts: an easy ticket has 1 stream, found 92% of the time (~178 of 193). A hard "
         "ticket has ~5.6 correct Value Streams on average — the search finds ~4.9 of them (88%) but "
         "lands the complete set only 63% of the time (~113 of 180). So on a hard ticket we usually "
         "catch ~4.9 of ~5.6 streams but miss one or two from the long tail."),
        ("4. Showing more tickets barely helps", c4,
         "Showing 6, 8, or 10 past tickets. Average coverage climbs only 90% → 94% and full coverage "
         "78% → 85% — small, diminishing gains for each extra ticket. So 6 examples is enough; more adds "
         "length without much benefit."),
        ("5. The right answer is usually at the very top", c5,
         "For each ticket, the position of the first pulled ticket that carries a correct Value Stream. "
         "For 288 of 373 tickets it's position #1 — the top result is usually already right. Only 9 "
         "tickets found nothing correct at all. So the search not only finds the right streams, it "
         "ranks them first."),
    ]
    for title, chart, text in sections:
        doc.add_heading(title, level=1)
        for para in text.split("\n\n"):
            doc.add_paragraph(para)
        doc.add_picture(chart, width=Inches(6.0))
        if chart is c1:  # the found-all/some/none coverage split, with each group's avg coverage
            doc.add_paragraph("How complete is each group? Even the 'found some' group finds about "
                              "two-thirds of their streams on average:")
            ct = doc.add_table(rows=1, cols=3); ct.style = "Light Grid Accent 1"
            for c, h in zip(ct.rows[0].cells, ["Group", "% of tickets", "Of their streams, found (avg)"]):
                c.text = h
            for g, pct, cov in [("Found ALL", "78%", "100%"), ("Found SOME", "18%", "~68% (≈2 of 3)"),
                                ("Found NONE", "4%", "0%")]:
                cells = ct.add_row().cells
                cells[0].text, cells[1].text, cells[2].text = g, pct, cov

    doc.add_heading("All the numbers", level=1)
    t = doc.add_table(rows=1, cols=4); t.style = "Light Grid Accent 1"
    for c, h in zip(t.rows[0].cells, ["Measure (per ticket)", "Show 6", "Show 8", "Show 10"]):
        c.text = h
    for label, key in [("Avg coverage (fraction of streams found)", "recall"),
                       ("Found at least one correct stream", "hit"),
                       ("Found EVERY correct stream", "fully_covered")]:
        cells = t.add_row().cells
        cells[0].text = label
        for i, v in enumerate(d[key]):
            cells[i + 1].text = f"{v:.0%}"

    doc.add_heading("Plain-language glossary", level=1)
    gl = doc.add_table(rows=1, cols=2); gl.style = "Light Grid Accent 1"
    gl.rows[0].cells[0].text, gl.rows[0].cells[1].text = "Term", "What it means"
    for term, mean in [
        ("Value Stream", "The business category a ticket belongs to — what we predict."),
        ("Coverage", "Of a ticket's correct Value Streams, how many showed up in the pulled examples."),
        ("Found everything", "All of a ticket's correct Value Streams were found — none missed."),
        ("Easy / hard ticket", "Easy = 1 correct Value Stream; hard = 2 or more."),
        ("@6 / @8 / @10", "When showing the top 6 / 8 / 10 pulled past tickets."),
    ]:
        cells = gl.add_row().cells
        cells[0].text, cells[1].text = term, mean

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    print(f"report -> {OUT}")


if __name__ == "__main__":
    build()
