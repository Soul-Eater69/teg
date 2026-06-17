"""Corrected Figure 2 — Value Stream Prediction Flow (no index VS, no lanes, no scoring, no pool)."""
from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

C_IO   = ("#2E6DA4", "#1F4E79", "white")   # input/output  (fill, edge, text)
C_DATA = ("#E4F1E4", "#4C9A4C", "#1c1c1c") # retrieval / data
C_LLM  = ("#FBE9CC", "#E0922F", "#1c1c1c") # LLM call
C_GATE = ("#FCE3C8", "#E0922F", "#1c1c1c") # approval gate

fig, ax = plt.subplots(figsize=(9.2, 12.4))
ax.set_xlim(0, 100); ax.set_ylim(0, 138); ax.axis("off")

def box(cx, cy, w, h, title, body, colors, *, title_size=11, body_size=9.2, rounding=2.2):
    fill, edge, txt = colors
    ax.add_patch(FancyBboxPatch((cx-w/2, cy-h/2), w, h,
                 boxstyle=f"round,pad=0.3,rounding_size={rounding}",
                 fc=fill, ec=edge, lw=1.6))
    ax.text(cx, cy + h/2 - 3.3, title, ha="center", va="top", fontsize=title_size,
            weight="bold", color=txt)
    if body:
        ax.text(cx, cy + h/2 - 7.0, body, ha="center", va="top", fontsize=body_size,
                color=txt, linespacing=1.35)

def arrow(x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                 mutation_scale=18, lw=1.7, color="#2E6DA4"))

ax.text(50, 135, "Figure 2. Value Stream Prediction Flow", ha="center",
        fontsize=15, weight="bold", color="#1F4E79")

# 1. Input
box(50, 128, 30, 6.5, "IDMT Ticket ID", "", C_IO, title_size=11.5)
arrow(50, 124.7, 50, 121.5)

# 2. Condense
box(50, 116, 74, 9.5,
    "Condense Step",
    "summaryFields (retrieval & routing) + rawText  —  written to Cosmos", C_DATA, body_size=9)
arrow(50, 111.2, 50, 108)

# split to two sources
arrow(50, 108, 27, 102.5)
arrow(50, 108, 73, 102.5)

# 3a. Historical retrieval (left)
box(27, 90, 44, 22,
    "Historical Ticket Retrieval",
    "Embed the new ticket's summary →\n"
    "top 6 similar historical ER tickets\n"
    "from idp_teg_data (historic docs\n"
    "ONLY; retrieval-only).\n"
    "Each ticket's summary + VS\n"
    "ground-truth read from Cosmos.\n"
    "Shown to SME for relevance.", C_DATA, body_size=8.6)

# 3b. VS catalogue (right)
box(73, 90, 44, 22,
    "Value Stream Catalogue",
    "ALL 50 approved Value Streams\n"
    "from the Azure SQL DB\n"
    "(org gold catalogue;\n"
    "integration pending).\n\n"
    "Not in the index, not retrieved —\n"
    "the full set is passed in whole.", C_DATA, body_size=8.6)

arrow(27, 79, 40, 72.5)
arrow(73, 79, 60, 72.5)

# 4. LLM selection
box(50, 62, 80, 16,
    "LLM Value Stream Selection  (single call, strict structured output)",
    "Reads the new ticket's RAW idea-card text (~24k tok)\n"
    "+ all 50 Value Streams + the 6 historical tickets (as summaries).\n"
    "No lanes, no candidate merge, no scoring/ranking, no review-pool limit.\n"
    "Picks the relevant Value Streams directly.", C_LLM, title_size=10.5, body_size=8.8)
arrow(50, 54, 50, 50.5)

# 5. Response
box(50, 43, 80, 12,
    "ValueStreamResponse",
    "Exactly N Value Streams (default 10) → ranked recommendations\n"
    "recommendations[{ valueStreamId, valueStreamName, confidence,\n"
    "supportType (direct|implied), reason, sourceTickets (implied only) }]",
    C_IO, body_size=8.6)
arrow(50, 37, 50, 33.5)

# 6. HITL
box(50, 27, 56, 9.5,
    "Human Approval Gate (HITL)",
    "SME confirms the approved Value Stream set  →  Theme Generation (Figure 3)",
    C_GATE, title_size=10.5, body_size=8.6)

# legend
leg = [("Retrieval / data", C_DATA), ("LLM call", C_LLM), ("Approval gate", C_GATE),
       ("Input / Output", C_IO)]
x = 12
for label, (fill, edge, _) in leg:
    ax.add_patch(FancyBboxPatch((x, 16), 3.4, 3.0, boxstyle="round,pad=0.1,rounding_size=0.6",
                 fc=fill, ec=edge, lw=1.4))
    ax.text(x+4.2, 17.5, label, ha="left", va="center", fontsize=8.8)
    x += 22

fig.tight_layout()
fig.savefig("/tmp/figure2_corrected.png", dpi=150, bbox_inches="tight", facecolor="white")
print("wrote /tmp/figure2_corrected.png")
