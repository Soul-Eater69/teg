"""Ingestion TDD flowcharts: (1) Stage 0 identification funnel, (2) Stage 1 pipeline, (3) storage."""
from __future__ import annotations
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys; sys.path.insert(0, "/Users/mahesh/projects/teg/scripts")
from fig_common import node, arrow, C_IO, C_DATA, C_LLM, C_DET, C_GATE

OUT = "/Users/mahesh/projects/teg/docs/ingestion_charts"
import os; os.makedirs(OUT, exist_ok=True)

C_FILT = ("#D7E8F5", "#3F7CAE", "#13405e")   # funnel filter
C_EMB  = ("#D7E8F5", "#3F7CAE", "#13405e")


# ---------- Figure 1: Stage 0 identification funnel ----------
def fig1():
    fig, ax = plt.subplots(figsize=(8.4, 10.6)); ax.set_xlim(0, 100); ax.set_ylim(0, 128); ax.axis("off")
    ax.text(50, 124, "Stage 0 — Ticket identification funnel (Neo4j)", ha="center", fontsize=13.5,
            weight="bold", color="#1F4E79")
    rows = [
        ("Neo4j JIRA graph", "all issue nodes", C_DATA, 96),
        ("L2 — IDMT Engagement Request, recent", "key IDMT-*, issueType = Engagement Request,\ncreated ≥ 2023-01-01", C_FILT, 56),
        ("L3 — not in a dead status", "status NOT IN {Cancelled, Blocked, New Request}", C_FILT, 52),
        ("L4 — implemented by a linked issue", "≥1 inbound 'implemented by' link → linked keys", C_FILT, 48),
        ("L5 — the linked issue is a live Theme", "issueType = Theme, status NOT IN {To Do, Cancelled}", C_FILT, 52),
        ("L6 — the Theme carries a Value Stream", "Theme.businessValueStreams matches {VSR…}", C_FILT, 40),
        ("Usable ticket cohort", "distinct IDMT keys → list (no content read)", C_IO, 56),
    ]
    y = 114; widths = [w for *_, w in rows]
    for i, (title, body, col, w) in enumerate(rows):
        h = node(ax, 50, y, w, title, body, col, ts=10.0, bs=8.0,
                 h=11 if i not in (0, len(rows)-1) else 9)
        if i < len(rows) - 1:
            arrow(ax, 50, y - h/2, 50, y - h/2 - 3)
        y -= h + 6
    fig.savefig(f"{OUT}/fig1_identification.png", dpi=150, bbox_inches="tight", facecolor="white")
    print("fig1")


# ---------- Figure 2: Stage 1 per-ticket pipeline ----------
def fig2():
    fig, ax = plt.subplots(figsize=(9.0, 12.8)); ax.set_xlim(0, 100); ax.set_ylim(0, 140); ax.axis("off")
    ax.text(50, 136, "Stage 1 — Per-ticket ingestion", ha="center", fontsize=14, weight="bold", color="#1F4E79")
    steps = [
        ("IDMT ticket id", "from the Stage 0 cohort", C_IO, "", 7),
        ("Fetch from Jira", "Engagement Request + issue links →\nlinked Theme keys → fetch each Theme", C_DET, "no LLM", 12),
        ("Extract attachments", "pdf · pptx · docx  (PowerPoint → PDF → Word)", C_DET, "no LLM", 9),
        ("Assemble raw text", "description + attachments → ~24k-token budget", C_DET, "no LLM", 9),
        ("Condense", "summary fields (businessSummary, keyTerms,\nproblem, capability, stakeholders, systems)", C_LLM, "LLM · gpt-5-mini-idp", 12),
        ("Read each Theme", "title, description, Value Stream\n(from the Business Value Stream field)", C_DET, "no LLM", 12),
        ("Embed searchText", "text-embedding-3-small-idp (1536-d)", C_EMB, "embedding", 9),
        ("Write outputs", "Cosmos ER doc + Theme docs  ·  idp_teg_data index doc", C_DATA, "", 9),
    ]
    y = 128
    for i, (title, body, col, badge, h) in enumerate(steps):
        hh = node(ax, 50, y, 64, title, body, col, ts=10.5, bs=8.2, h=h)
        if badge:
            ax.text(84, y, badge, ha="left", va="center", fontsize=7.6, style="italic",
                    color=col[1])
        if i < len(steps) - 1:
            arrow(ax, 50, y - hh/2, 50, y - hh/2 - 3)
        y -= hh + 5.5
    fig.savefig(f"{OUT}/fig2_pipeline.png", dpi=150, bbox_inches="tight", facecolor="white")
    print("fig2")


# ---------- Figure 3: storage ----------
def fig3():
    fig, ax = plt.subplots(figsize=(10.2, 7.6)); ax.set_xlim(0, 100); ax.set_ylim(0, 86); ax.axis("off")
    ax.text(50, 82, "Storage — what goes where", ha="center", fontsize=14, weight="bold", color="#1F4E79")
    node(ax, 50, 74, 46, "Per-ticket ingestion output", "", C_IO, ts=10.5, h=7)
    arrow(ax, 50, 70.5, 28, 64); arrow(ax, 50, 70.5, 72, 64)
    node(ax, 26, 50, 44, "Cosmos — system of record",
         "Engagement Request document\n(id, key, sourceId, …, properties:\ndescription, summary, businessSummary,\nkeyTerms, businessProblem,\nbusinessCapability, stakeholders,\nsystemsAndProducts, rawText)\n\n+ one Theme document per linked Theme\n(properties: summary, description,\nvalueStream)  — linked via parentRef", C_DATA, ts=10, bs=7.6, h=30)
    node(ax, 74, 54, 44, "idp_teg_data — AI search index",
         "retrieval-only:\nkey, sourceId, entityType, status,\nsearchText, content_vector\n(ER documents only)", C_DATA, ts=10, bs=7.8, h=18)
    node(ax, 74, 28, 44, "Azure SQL DB — governed catalogue",
         "Value Stream / Stage / L2 / L3\ngold data — consumed as-is,\nNOT produced by ingestion", C_DET, ts=10, bs=7.8, h=14)
    fig.savefig(f"{OUT}/fig3_storage.png", dpi=150, bbox_inches="tight", facecolor="white")
    print("fig3")


fig1(); fig2(); fig3()
print("done ->", OUT)
