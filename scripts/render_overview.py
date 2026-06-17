"""Minimal, client-facing overview: the flow + why each LLM call is needed."""
from __future__ import annotations
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

LLM  = ("#FBE9CC", "#E0922F", "#1c1c1c")   # LLM call
CODE = ("#EAEAEA", "#9A9A9A", "#444444")   # automatic (no LLM)
GATE = ("#FCE3C8", "#E0922F", "#1c1c1c")   # human
IO   = ("#2E6DA4", "#1F4E79", "white")

fig, ax = plt.subplots(figsize=(11.6, 9.0))
ax.set_xlim(0, 100); ax.set_ylim(0, 78); ax.axis("off")
ax.text(50, 75, "How it works — and why each step needs an LLM", ha="center",
        fontsize=16, weight="bold", color="#1F4E79")

# left column: the flow.  right column: the "why".
BX, BW = 8, 42        # box left, width
WHY = 54              # why-text x

def step(cy, title, colors, why="", *, h=7.2, badge=""):
    fill, edge, txt = colors
    ax.add_patch(FancyBboxPatch((BX, cy-h/2), BW, h, boxstyle="round,pad=0.3,rounding_size=1.6",
                 fc=fill, ec=edge, lw=1.7))
    ax.text(BX+BW/2, cy+(1.1 if badge else 0), title, ha="center", va="center",
            fontsize=11.5, weight="bold", color=txt)
    if badge:
        ax.text(BX+BW/2, cy-1.9, badge, ha="center", va="center", fontsize=8.5,
                style="italic", color=edge)
    if why:
        ax.text(WHY, cy, why, ha="left", va="center", fontsize=9.6, color="#333333", linespacing=1.3)

def down(y1, y2):
    ax.add_patch(FancyArrowPatch((BX+BW/2, y1), (BX+BW/2, y2), arrowstyle="-|>",
                 mutation_scale=20, lw=2.0, color="#2E6DA4"))

ys = [66, 56.5, 47, 37.5, 28, 18.5, 9]
step(ys[0], "Idea card", IO, "The business request (idea card + attachments).")
down(ys[0]-3.6, ys[1]+3.6)
step(ys[1], "1 · Understand it", LLM, "LLM — read the messy idea card and pull out the\nreal business problem. A keyword scan can't do this.", badge="LLM call")
down(ys[1]-3.6, ys[2]+3.6)
step(ys[2], "2 · Find similar past work", CODE, "Automatic search — no LLM. Finds the 6 most similar\npast tickets as precedent.", badge="no LLM")
down(ys[2]-3.6, ys[3]+3.6)
step(ys[3], "3 · Choose Value Streams", LLM, "LLM — judge which business areas the change touches,\nincluding the implied ones a rule would miss.", badge="LLM call")
down(ys[3]-3.6, ys[4]+3.6)
step(ys[4], "Human approval", GATE, "A person confirms the Value Streams before anything\nis written. Nothing is generated until they approve.", badge="human")
down(ys[4]-3.6, ys[5]+3.6)
step(ys[5], "4 · Write each Theme", LLM, "LLM — for each approved area, write the description,\nbusiness needs, stages and capabilities. This is the\nwriting work the tool is replacing.", badge="LLM calls")
down(ys[5]-3.6, ys[6]+3.6)
step(ys[6], "Assemble the package", CODE, "Automatic — no LLM. Stitch the pieces into the final\nTheme package for review.", badge="no LLM")

# footer note
ax.add_patch(FancyBboxPatch((10, 1.0), 80, 3.4, boxstyle="round,pad=0.2,rounding_size=0.8",
             fc="#F3F6FA", ec="#9DB6CF", lw=1.2))
ax.text(50, 2.7, "An LLM is used only for judgment and writing — everything mechanical stays automatic.",
        ha="center", va="center", fontsize=9.6, style="italic", color="#1F4E79")

fig.savefig("/tmp/flow_overview.png", dpi=150, bbox_inches="tight", facecolor="white")
print("wrote /tmp/flow_overview.png")
