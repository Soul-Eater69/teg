"""TDD Figure 3 — Theme Generation Flow (merged caps: 4 + N calls).

Recreated to match the docx figure family (fig_common style). The one fix vs the prior
render: Capabilities (L3) is drawn BELOW Stage Selection with an explicit "needs the
selected stages" arrow - it is sequential after Stage Selection, not parallel to it.
Renders /tmp/tdd_fig3.png.
"""
from __future__ import annotations
import sys; sys.path.insert(0, "/Users/mahesh/projects/teg/scripts")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from fig_common import node, arrow, band, legend, C_LLM, C_DET, C_GATE, C_IO, C_NOTE

fig, ax = plt.subplots(figsize=(9.2, 13.4))
ax.set_xlim(0, 100); ax.set_ylim(0, 150); ax.axis("off")
ax.text(50, 147, "Figure 3. Theme Generation Flow", ha="center", fontsize=14,
        weight="bold", color="#1F4E79")

# ---- Human approval gate ----
node(ax, 50, 139, 50, "Human Approval Gate (HITL)",
     "SME confirms the approved Value Stream set (Figure 2)", C_GATE, ts=10.5, bs=8.2, h=8)
arrow(ax, 50, 135, 50, 131)

# ---- TICKET-LEVEL band: 4 calls once for all VS ----
band(ax, 6, 96, 88, 35, "TICKET-LEVEL — once for ALL approved Value Streams (4 LLM calls)")
# top row: BODY, FRAMING, Stage Selection (parallel)
node(ax, 22, 122, 26, "Description BODY",
     "LLM ×1 · shared narrative\nbody, once for all VS", C_LLM, ts=9.2, bs=7.6, h=12)
node(ax, 50, 122, 26, "Description FRAMING",
     "LLM ×1 · per-VS intro\nparagraph, batched", C_LLM, ts=9.2, bs=7.6, h=12)
hST = node(ax, 78, 122, 26, "Stage Selection",
           "LLM ×1 · all VS →\nselectedStages per VS", C_LLM, ts=9.2, bs=7.6, h=12)
# Capabilities BELOW Stage Selection — sequential, needs the selected stages
node(ax, 78, 104, 26, "Capabilities (L3)",
     "LLM ×1 · ALL VS in ONE call;\nmatch work to governed L3", C_LLM, ts=9.2, bs=7.5, h=12)
arrow(ax, 78, 116, 78, 110)  # Stage Selection -> Capabilities
ax.text(80.5, 113, "needs the\nselected stages", ha="left", va="center",
        fontsize=7.4, style="italic", color="#b3401a", linespacing=1.15)

# fan into the band from the gate
arrow(ax, 50, 131, 22, 128); arrow(ax, 50, 131, 50, 128); arrow(ax, 50, 131, 78, 128)

# ---- salvage note (plain italic line, matches the figure family) ----
arrow(ax, 50, 96, 50, 92)
ax.text(50, 90, "Salvage: an L3 placed under the wrong stage is reassigned to its true owning "
        "stage —\nstrict stage isolation keeps 0 mislink in the output.",
        ha="center", va="center", fontsize=8.4, style="italic", color="#5a4a66", linespacing=1.3)

# ---- description concat note ----
ax.text(50, 84, "Per approved Value Stream, the Theme description = that VS's FRAMING paragraph "
        "+ the shared BODY,\nconcatenated into one running narrative.",
        ha="center", va="center", fontsize=8.4, style="italic", color="#5a4a66", linespacing=1.3)
arrow(ax, 50, 81, 50, 70)

# ---- PER-VS band: Business Needs (1 call each) ----
band(ax, 6, 56, 88, 14, "PER APPROVED VALUE STREAM — fans out across all N VSs (1 LLM call each)")
node(ax, 50, 62, 40, "Business Needs",
     "LLM ×N · 1 call PER VS — needs per selected\nstage, grounded in the content", C_LLM,
     ts=9.6, bs=7.7, h=9)
arrow(ax, 50, 56, 50, 52)

# ---- deterministic tail ----
node(ax, 50, 47, 70, "L2 derived 1:1 from the selected L3  ·  no separate LLM call",
     "", C_DET, ts=9.6, bs=8.0, h=7)
arrow(ax, 50, 43.5, 50, 39.5)
node(ax, 50, 34, 80, "Theme Package Assembly  ·  deterministic",
     "themeTitle = «idmtTicketTitle -- valueStreamName»  ·  assemble description + stages + "
     "business needs + L3/L2  ·  one package per VS.", C_DET, ts=10, bs=7.9, h=9)
arrow(ax, 50, 29.5, 50, 25.5)
node(ax, 50, 21, 60, "ThemeGenerationResponse",
     "one THEME worklet per approved Value Stream", C_IO, ts=10.5, bs=8.2, h=8)

legend(ax, [("LLM call", C_LLM), ("Deterministic (no model)", C_DET),
            ("Human gate", C_GATE), ("Note / derived", C_NOTE), ("Input / Output", C_IO)],
       y=10, x0=6, dx=18.5, fs=8.0)

fig.savefig("/tmp/tdd_fig3.png", dpi=150, bbox_inches="tight", facecolor="white")
print("wrote /tmp/tdd_fig3.png")
