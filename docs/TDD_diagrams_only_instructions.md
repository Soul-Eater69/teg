# TDD v10 — DIAGRAMS ONLY: build in Figma and replace the 3 figures

The text in `tdd_updated_v10.docx` is correct. Only the **3 diagrams are still the old images** and
must be rebuilt. This file is self-contained — you only need this to fix the figures.

## First: clean up the duplicate images in the doc
The doc currently has **6 images** but only needs **3 figures**. There are leftover/duplicate
images at the figure spots:
- **§3 Ingestion Design Flow** → 1 image → this is **Figure 1**
- **§5 Data Science Solution** → **2 images stacked** before the "Figure 2" caption, plus **1 more**
  under §5.1 labeled "Figure 2a" → keep **ONE** here (Figure 2) and **DELETE the other two**.
- **§6 Theme Generation Solution** → **2 images stacked** before the "Figure 3" caption → keep
  **ONE** (Figure 3) and **DELETE the other one**.

So the end state is exactly **3 images**: Figure 1 (§3), Figure 2 (§5), Figure 3 (§6). Delete the
"Figure 2a" caption line too — it's merged into Figure 2 now.

## How to build each diagram in Figma (do this once, repeat per figure)
1. Open Figma → **New design file** (or use FigJam for faster flowcharts).
2. For each figure: drop **rounded rectangles** for the boxes, type the label inside each, and
   connect them with **arrows** in the direction shown. Use a light fill (match the existing doc
   style — pale blue/grey boxes, dark text).
3. Group the whole diagram, then **Export** the frame as **PNG at 2x** (right panel → Export → +,
   set 2x, PNG).
4. In Word: click the old image → Delete → Insert → Picture → choose your PNG. Keep the existing
   "Figure N." caption line below it.

Build them top-to-bottom unless noted. Text in `"quotes"` is the box label; `→` is an arrow.

---

## FIGURE 1 — Ingestion flow  (replaces the image in §3)

Two columns (swimlanes). Left column is the main nightly batch; right column is the catalogue.

**Left lane — "Historic ER ingestion (nightly batch)"** (vertical chain, each box → next):
```
"iTech DB audit
 (eligible ERs after 2023-01-01 · Theme links present · issue type = ER ·
  keep only valid / partially-valid approved VS ground truth)"
   →
"Jira API fetch
 (description · attachments · linked Themes / GROUPs)"
   →
"Attachment extraction
 (idea-card priority: PPT/PPTX → PDF → DOC/DOCX · top 4 · cap context)"
   →
"Condense — single LLM pass
 → summaryFields + generationSignals"
   →
"Value Stream resolution
 (each Theme summary → approved 50-VS catalogue · fuzzy + LLM confirm ·
  drop Themes that don't resolve)"
   →
"Build documents:
 • Cosmos IDMT/ER doc (properties + themes[] GT = id + name only)
 • Cosmos Theme docs (one per GROUP)
 • Historical index doc (content + content_vector, embedded)"
   →
"Persist:  Cosmos (system of record)   +   idp_teg_data (AI Search · EngagementRequest lane)"
```

**Right lane — "Value Stream catalogue ingestion"** (separate short chain):
```
"Sightline catalogue"
   →
"Dedupe / organize / tag"
   →
"Cosmos catalogue doc (VS → stages → L3/L2/L1)
 +  idp_teg_data (ValueStream lane, embedded)"
```

> ⚠️ KEY CHANGE FROM THE OLD FIGURE 1: there is **NO "direct/implied classification" box** anymore.
> If the old diagram has a classification step after VS resolution, leave it out. The themes[]
> ground truth carries only valueStreamId + valueStreamName.

---

## FIGURE 2 — Data science / Value Stream selection flow  (replaces the image in §5)

Top-to-bottom, with the two retrieval lanes side-by-side in the middle.

```
"IDMT ticket id"
   →
"Condense → summaryFields (retrieval + LLM context) + generationSignals"
   →
   ┌──────── two retrieval lanes on idp_teg_data, IN PARALLEL ────────┐
   │                                  │                               │
 "Value Stream catalogue lane        "Historical Engagement Request lane
  entityType = ValueStream            entityType = EngagementRequest
  Hybrid (BM25 + vector)              Hybrid (BM25 + vector)
   + semantic reranker                 + semantic reranker
  → top 50 VS candidates"             → top 6 historical tickets (shown to SME)"
   │                                  │                               │
   └──────────────────┬───────────────────────────────────────────────┘
                      →
"Candidate merge → 3 lanes:
 semantic_plus_historic | historic_only | semantic_only"
                      →
"Ranking:
 • semantic (reranker) score
 • historical evidence — co-occurrence frequency + best/weighted support score
 • GENERIC-STREAM PENALTY — demote broad / high-false-positive-rate streams
   UNLESS earned by ≥3 supporting historical tickets
 • validation against the approved 50-VS registry"
                      →
"Review pool (window = 18 · greedy backfill so it's never starved)"
                      →
"Single selection LLM call  (strict structured output)"
                      →
"Exactly N value streams (default 10) → ranked recommendations"
                      →
"HITL approval — SME confirms the final VS set"
```

> ⚠️ KEY CHANGES FROM THE OLD FIGURE 2:
> 1. The **historical lane** used to say "Vector similarity over content_vector" — change it to
>    **"Hybrid (BM25 + vector) + semantic reranker"** (same as the catalogue lane).
> 2. In the **Ranking** box: REMOVE "support type / reason / snippet"; ADD the **generic-stream
>    penalty** bullet.
> 3. Label the selection LLM box **"strict structured output."**
> 4. Delete the old "Figure 2a" second image — this single figure replaces both.

---

## FIGURE 3 — Theme generation flow  (replaces the image in §6)

This is the biggest change. Draw it as **two horizontal bands**: a TICKET-LEVEL band (work done
once for all approved VS) and a PER-VS band (work that fans out per VS).

```
"HITL approval of N approved value streams"
            │
            ▼
┌───── BAND 1 · TICKET-LEVEL — once for ALL approved VS · 3 calls IN PARALLEL ─────┐
│                                                                                  │
│  "Description BODY            "Description FRAMING          "Stage selection      │
│   (shared · VS-agnostic ·      (ONE batched call ·          (ONE batched call ·   │
│    availability + initiative   one opening paragraph        all VS · each VS      │
│    + capabilities sections)    per VS)                      picks from its OWN    │
│   → 1 call"                   → 1 call"                      candidate stages)    │
│                                                            → 1 call               │
│                                                            → {vs_id: stages}"     │
└──────────────────────────────────────────────────────────────────────────────────┘
            │  assemble per VS:  theme description = "Theme Description:" + framing[vs] + shared body
            ▼
┌───── BAND 2 · PER APPROVED VS — fan out across VS · 2 calls each IN PARALLEL ─────┐
│                                                                                  │
│   "Business Needs                          "Capabilities                          │
│    (per VS · over its selected stages ·     (ONE call per VS · ALL its stages ·   │
│     grouped Value Stage → feature → needs)   per stage pick L3 from that stage's  │
│   → 1 call / VS"                             candidates · L2 derived 1-1, no call) │
│                                            → 1 call / VS"                          │
└──────────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
"Assemble Theme package per VS:
 deterministic title ('<ticket title> - <VS name>') + description + selected stages
 + Business Needs + L2/L3 capabilities"
            │
            ▼
"Theme packages → SME review"
```

> ⚠️ KEY CHANGES FROM THE OLD FIGURE 3 (the old one fanned every generator out per VS):
> - **Theme Description** is no longer one full call per VS — it is a **shared body (1 call)** plus a
>   **batched framing call for all VS (1 call)**, assembled per VS.
> - **Stage selection** is **one batched call for all VS**, not per VS.
> - Those three (body, framing, stages) sit in **Band 1 — ticket-level, run once, in parallel**.
> - **Capabilities** is **one call per VS** (covering all its stages), not one call per stage.
> - **Business Needs** stays per VS (Band 2) — it is the only generator that must stay per VS.
> - Optional footnote on the figure: "≈60 → ≈23 LLM calls for 10 VS / ~3 stages each."
> - Delete the old second image stacked here; this single figure replaces both.

---

## Final check before saving
- Exactly **3 images** in the doc: Figure 1 (§3), Figure 2 (§5), Figure 3 (§6).
- The "Figure 2a" caption + its extra image are **removed**.
- Figure 1 has **no classification box**.
- Figure 2 historical lane says **hybrid + semantic reranker**, ranking shows the **generic penalty**.
- Figure 3 shows **two bands** (ticket-level batched vs per-VS), not a per-VS fan-out for everything.
- Save as `tdd_updated_v10.docx` (overwrite) or `v11` if you want to keep v10.
