"""Generation flow (full runtime, no ingestion): idea card -> Theme packages.
Theme generation is a DAG: Description -> straight to the package; Stage Selection gates
Business Needs + Capabilities. Every LLM box says why an LLM is used. Boxes auto-size to text."""
from __future__ import annotations
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

LLM  = ("#FBE9CC", "#E0922F", "#1c1c1c")
CODE = ("#EAEAEA", "#9A9A9A", "#444444")
GATE = ("#FCE3C8", "#E0922F", "#1c1c1c")
IO   = ("#2E6DA4", "#1F4E79", "white")
ORG  = "#9a5a00"

PAD, TITLE_H, BADGE_H, LINE_H = 2.2, 3.4, 2.2, 1.7


def _bh(title, badge, why):
    lines = (why.count("\n") + 1) if why else 0
    block = (TITLE_H if title else 0) + (BADGE_H if badge else 0) + lines * LINE_H
    return block + 2 * PAD, block


def box(ax, cx, cy, w, title, why, colors, *, ts=10.6, badge="", wfs=8.2):
    """Auto-sized rounded box; title + optional italic badge + why text, block centered. Returns h."""
    fill, edge, txt = colors
    h, block = _bh(title, badge, why)
    ax.add_patch(FancyBboxPatch((cx-w/2, cy-h/2), w, h, boxstyle="round,pad=0.3,rounding_size=1.4",
                 fc=fill, ec=edge, lw=1.6))
    y = cy + block/2
    if title:
        ax.text(cx, y, title, ha="center", va="top", fontsize=ts, weight="bold", color=txt); y -= TITLE_H
    if badge:
        ax.text(cx, y, badge, ha="center", va="top", fontsize=7.9, style="italic", color=edge); y -= BADGE_H
    if why:
        ax.text(cx, y, why, ha="center", va="top", fontsize=wfs, color="#3a3a3a", linespacing=1.25)
    return h


def arr(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=15,
                 lw=1.7, color="#2E6DA4"))


fig, ax = plt.subplots(figsize=(11.4, 17.4))
ax.set_xlim(0, 100); ax.set_ylim(0, 176); ax.axis("off")
ax.text(50, 173, "Generation flow — idea card to Theme packages", ha="center",
        fontsize=15.5, weight="bold", color="#1F4E79")

# ---------- linear steps (cursor layout, no overlap by construction) ----------
W, GAP, y = 58, 3.4, 168.0
def stack(title, why, colors, badge=""):
    global y
    h, _ = _bh(title, badge, why)
    cy = y - h/2
    box(ax, 50, cy, W, title, why, colors, badge=badge)
    arr(ax, 50, cy - h/2, 50, cy - h/2 - GAP)
    y = cy - h/2 - GAP
    return cy

stack("Idea card", "the business request (idea card + attachments)", IO, badge="")
stack("1 · Understand it", "LLM — pull the real business problem out of the messy idea card", LLM, badge="LLM call")
stack("2 · Find similar past work", "no LLM — automatic search for the 6 most similar past tickets", CODE, badge="no LLM")
stack("3 · Choose Value Streams", "LLM — judge which business areas the change touches (incl. implied)", LLM, badge="LLM call")
appr_cy = stack("Human approval", "the SME confirms the Value Streams before anything is written", GATE, badge="human")

# ---------- theme-generation DAG (clean heading, arrows start below it) ----------
appr_bottom = appr_cy - _bh("Human approval", "human", "x")[0] / 2
head_y = appr_bottom - 4.0
arr(ax, 50, appr_bottom, 50, head_y + 2.2)                      # approval -> the step
ax.text(50, head_y, "4 · Write each approved Theme", ha="center", va="center",
        fontsize=12, weight="bold", color=ORG)

# 3 ticket-level calls: Description BODY, Description FRAMING, Stage Selection
hRow = _bh("x", "b", "one line")[0]
row1 = head_y - 7.0 - hRow / 2
hBODY = box(ax, 17, row1, 28, "Description BODY",
            "LLM — the shared Theme narrative", LLM, ts=9.6, badge="LLM · per ticket", wfs=7.8)
hFRM = box(ax, 46, row1, 28, "Description FRAMING",
           "LLM — a per-Value-Stream intro", LLM, ts=9.6, badge="LLM · per ticket", wfs=7.8)
hST = box(ax, 76, row1, 30, "Stage Selection",
          "LLM — which lifecycle stages it hits", LLM, ts=9.6, badge="LLM · per ticket", wfs=7.8)
# fan out from below the heading
arr(ax, 50, head_y - 2.0, 17, row1 + hBODY/2)
arr(ax, 50, head_y - 2.0, 46, row1 + hFRM/2)
arr(ax, 50, head_y - 2.0, 76, row1 + hST/2)

ax.text(76, row1 - hST/2 - 3.2, "↓ sequential — needs the selected stages", ha="center", va="center",
        fontsize=8.2, style="italic", color="#b3401a")
row2 = row1 - hST/2 - 13
hBN = box(ax, 62, row2, 26, "Business Needs",
          "LLM — needs per selected stage,\ngrounded in the card", LLM, ts=9.6, badge="LLM · per VS", wfs=7.7)
hCAP = box(ax, 88, row2, 22, "Capabilities (L3)",
           "LLM — match to the governed\nL3 capabilities", LLM, ts=9.4, badge="LLM · per VS", wfs=7.7)
# stage selection -> per-VS boxes
arr(ax, 76, row1 - hST/2, 62, row2 + hBN/2)
arr(ax, 76, row1 - hST/2, 88, row2 + hCAP/2)

# converge to assemble: a wide box, each producer drops to a DISTINCT point on the top edge
# (kept in left-to-right order so the lines never cross), with a generous gap for the arrows.
asm = row2 - max(hBN, hCAP) / 2 - 13
hA = box(ax, 50, asm, 84, "Assemble the package",
         "no LLM — stitch the pieces into one Theme package per Value Stream", CODE, ts=10.5, badge="no LLM")
top = asm + hA / 2
arr(ax, 17, row1 - hBODY/2, 18, top)     # BODY  -> far left
arr(ax, 46, row1 - hFRM/2, 40, top)      # FRAMING
arr(ax, 62, row2 - hBN/2, 60, top)       # Business Needs
arr(ax, 88, row2 - hCAP/2, 82, top)      # Capabilities -> far right

# ---------- why-parallel note ----------
ny = asm - hA/2 - 6
ax.add_patch(FancyBboxPatch((6, ny-15, ), 88, 15, boxstyle="round,pad=0.3,rounding_size=1.0",
             fc="#F3F6FA", ec="#9DB6CF", lw=1.3))
ax.text(50, ny-1.6, "Why parallel — and the one place it's sequential", ha="center", va="top",
        fontsize=10.4, weight="bold", color="#1F4E79")
ax.text(50, ny-5.2,
        "• Description is independent of the stages, so it runs alongside everything and feeds the package directly.\n"
        "• Stage Selection and the per-Value-Stream calls are batched and run in parallel where they can.\n"
        "• The ONE sequential link: Business Needs and Capabilities need the SELECTED STAGES, so they wait\n"
        "   for Stage Selection. Nothing else waits — wall-clock stays ~flat (≈15s) as Value Streams grow.",
        ha="center", va="top", fontsize=8.6, color="#333", linespacing=1.45)

fig.savefig("/tmp/generation_flow.png", dpi=150, bbox_inches="tight", facecolor="white")
print("wrote /tmp/generation_flow.png")
