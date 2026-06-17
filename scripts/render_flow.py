"""Master end-to-end flow — where LLMs are invoked, where not, and the call counts.
Call count is in the title; colour encodes LLM vs embedding vs deterministic vs human."""
from __future__ import annotations
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys; sys.path.insert(0, "/tmp")
from fig_common import node, arrow, band, legend

C_IO   = ("#2E6DA4", "#1F4E79", "white")
C_LLM  = ("#FBE9CC", "#E0922F", "#1c1c1c")
C_EMB  = ("#D7E8F5", "#3F7CAE", "#13405e")
C_DET  = ("#EAEAEA", "#9A9A9A", "#1c1c1c")
C_GATE = ("#FCE3C8", "#E0922F", "#1c1c1c")

fig, ax = plt.subplots(figsize=(12.8, 18.4))
ax.set_xlim(0, 100); ax.set_ylim(0, 206); ax.axis("off")
ax.text(50, 202, "End-to-End Flow — where an LLM is needed (and where it is NOT)",
        ha="center", fontsize=15.5, weight="bold", color="#1F4E79")

# ============ PHASE A: INGESTION ============
band(ax, 4, 130, 92, 64, "PHASE A — INGESTION  (offline, per historical ticket — builds the corpus)")

h = node(ax, 50, 186, 62, "Jira fetch — ticket + attachments + linked Themes/Epics   ·   no LLM",
         "Pull the source packet and its ground-truth links (API + parsing).", C_DET, ts=10, bs=8.2)
arrow(ax, 50, 186 - h/2, 50, 180)
h = node(ax, 50, 175, 62, "Attachment extraction + idea-card detection   ·   no LLM",
         "PPT→PDF→DOC priority; pick the idea card; extract text (≤8). Rules only.", C_DET, ts=10, bs=8.2)
arrow(ax, 50, 175 - h/2, 50, 169)
h = node(ax, 50, 164, 62, "Raw idea-card text assembly   ·   no LLM",
         "Greedy pack into a ~24k-token budget in source-priority order.", C_DET, ts=10, bs=8.2)
arrow(ax, 50, 164 - h/2, 50, 158)

node(ax, 27, 151, 40, "Condense   ·   LLM ×1",
     "Summarize the raw packet →\nsummaryFields + rawText.", C_LLM, ts=10, bs=8.0, h=13)
node(ax, 73, 151, 40, "Ground-truth extraction   ·   no LLM",
     "Read VS-Stage field + Epics →\ncanonicalize to catalogue.", C_DET, ts=10, bs=8.0, h=13)
arrow(ax, 27, 144.5, 50, 140); arrow(ax, 73, 144.5, 50, 140)
node(ax, 50, 135, 66, "Embed summaryFields → write Cosmos (SoR) + idp_teg_data index   ·   embedding",
     "Cosmos = durable docs + ground truth.   Index = searchText + content_vector only.",
     C_EMB, ts=10, bs=8.0, h=10)

# ============ PHASE B: RUNTIME ============
band(ax, 4, 6, 92, 118, "PHASE B — RUNTIME  (per new ticket → Theme packages)")

h = node(ax, 50, 118, 40, "New IDMT ticket id", "", C_IO, ts=11)
arrow(ax, 50, 118 - h/2, 50, 113)
h = node(ax, 50, 108, 62, "Condense the new ticket   ·   LLM ×1",
         "Same summarizer → summaryFields (find) + rawText (decide).", C_LLM, ts=10, bs=8.2)
yb = 108 - h/2
arrow(ax, 50, yb, 50, yb-2); arrow(ax, 50, yb-2, 27, 99); arrow(ax, 50, yb-2, 73, 99)

node(ax, 27, 93, 42, "Retrieve top-6 historical   ·   embedding",
     "Embed the summary → vector search\nthe index (historic docs only). No LLM.", C_EMB, ts=9.6, bs=7.9, h=14)
node(ax, 73, 93, 42, "Load all 50 Value Streams   ·   no LLM",
     "From the Azure SQL gold catalogue.\nNot retrieved, not ranked — passed whole.", C_DET, ts=9.6, bs=7.9, h=14)
arrow(ax, 27, 86, 50, 81.5); arrow(ax, 73, 86, 50, 81.5)

h = node(ax, 50, 76, 70, "Value Stream Selection   ·   LLM ×1",
         "Read raw text + all 50 VS + 6 historical summaries → pick the relevant VS.", C_LLM, ts=10, bs=8.2)
arrow(ax, 50, 76 - h/2, 50, 68.5)
h = node(ax, 50, 64, 56, "Human Approval Gate (HITL)   ·   human",
         "SME confirms the approved Value Stream set.", C_GATE, ts=10, bs=8.2)
arrow(ax, 50, 64 - h/2, 50, 57)

band(ax, 8, 37, 84, 17, "THEME GEN — ticket-level: all VS at once (3 LLM calls)")
for cx, t, b in [(22,"Stage Selection","LLM ×1 · all VS →\nselectedStages/VS"),
                 (50,"Description BODY","LLM ×1 · shared\nnarrative body"),
                 (78,"Description FRAMING","LLM ×1 · per-VS\nintro, batched")]:
    node(ax, cx, 45, 25, t, b, C_LLM, ts=9.2, bs=7.7, h=11)
arrow(ax, 50, 37, 50, 34)

band(ax, 8, 18, 84, 14, "THEME GEN — per VS: fans out (2 LLM calls each)")
node(ax, 30, 24.5, 30, "Business Needs", "LLM ×N · 1 call PER VS", C_LLM, ts=9.4, bs=7.7, h=8)
node(ax, 70, 24.5, 30, "Capabilities (L3)", "LLM ×N · 1 call PER VS", C_LLM, ts=9.4, bs=7.7, h=8)
arrow(ax, 50, 18, 50, 15)

node(ax, 50, 11, 86, "Deterministic assembly   ·   NO LLM",
     "L2 = unique parent of each selected L3 (id lookup)  ·  themeTitle = template  ·  "
     "salvage = id→owner routing  ·  concatenate → one Theme package per VS.", C_DET, ts=10, bs=7.9, h=8)

legend(ax, [("LLM call", C_LLM), ("Embedding / retrieval", C_EMB), ("Deterministic (no model)", C_DET),
            ("Human gate", C_GATE), ("Input / Output", C_IO)], y=1.5, x0=4, dx=19.5, fs=8.0)

fig.savefig("/tmp/master_flow.png", dpi=150, bbox_inches="tight", facecolor="white")
print("wrote /tmp/master_flow.png")
