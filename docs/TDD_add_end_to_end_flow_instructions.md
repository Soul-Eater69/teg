# TDD instructions — add the "End-to-end flow" overview section

**For:** the coworker maintaining the TDD.
**Goal:** add a single section that walks the **whole pipeline stage by stage** (ingestion → runtime →
theme generation), so a reader sees the complete journey and each stage's input/output and whether it
uses an LLM — in one place, before the detailed sections.

**Assets I've prepared (use these — do not redraw / re-derive):**
- Diagram: **`docs/flow_charts/master_flow.png`** (also on Desktop).
- Full source text: **`docs/end_to_end_flow.md`** (rendered `.pdf`/`.html` alongside). The text below is
  lifted from it — paste from the rendered doc to keep formatting.

This is a **text + one image** addition — fully doable by a text-editing LLM (no figure re-render).

---

## Where to put it

Add as a new **§1.2 "End-to-end flow"** right after the §1.1 system-overview figure (the
`TDD_add_llm_flow_instructions.md` one). If §1.1 wasn't added, put this at the end of §1 instead. It
sits up front as the map; §3–§6 remain the detailed spec.

> The two front-matter additions are complementary, not duplicates:
> §1.1 = the **one-figure** "where's the LLM" overview; §1.2 = the **stage-by-stage** walkthrough with
> I/O. If you only add one, add §1.2 (it contains the figure too).

## What to add

**1. Intro line:**
> *The pipeline has two phases. Phase A (ingestion) runs offline over historical tickets to build the
> corpus (Cosmos system-of-record + the retrieval index). Phase B (runtime) runs per new ticket to
> produce Theme packages, reusing the same Condense step and reading what Phase A stored.*

**2. The figure** `master_flow.png` (if not already inserted as Figure 0 by the §1.1 instructions —
otherwise just reference "Figure 0").

**3. Two stage tables** — copy from `docs/end_to_end_flow.md`. Keep them compact (one row per stage):

*Phase A — Ingestion*

| stage | LLM? | input → output | key rule |
|---|---|---|---|
| Jira fetch | no | ticket id → raw packet + linked Theme/Epic ids | ER after 2023-01-01 with a linked Theme |
| Attachment extraction + idea-card detection | no | attachments → extracted text | PPT→PDF→DOC, up to 8 |
| Raw text assembly | no | extracted texts → rawText | ~24k-token greedy pack, priority order |
| Condense | **LLM ×1** | rawText → summaryFields + rawText | summary to find, raw to decide |
| Ground-truth extraction | no | linked Themes/Epics → VS + stage/L3 GT | read the recorded answer; drop uncatalogued |
| Embed → Cosmos + index | embedding | retrieval text → SoR docs + index vectors | index = searchText + content_vector only |

*Phase B — Runtime*

| stage | LLM? | input → output | key rule |
|---|---|---|---|
| Condense (new ticket) | **LLM ×1** | rawText → summaryFields + rawText | reused from ingestion |
| Retrieve top-6 historical | embedding | summary → 6 similar tickets | retrieval query = summary |
| Load 50 Value Streams | no | — → 50 VS catalogue | Azure SQL gold data; not retrieved |
| Value Stream Selection | **LLM ×1** | raw text + 50 VS + 6 historical summaries → recommendations | raw is the lever; no lanes/ranking |
| HITL approval | human | recommendations → approved VS set | nothing generates before this |
| Stage Selection | **LLM ×1** | raw + per-VS candidate stages → selectedStages/VS | all VS batched; no count cap; salvage |
| Description BODY + FRAMING | **LLM ×2** | raw (+ per-VS detail for framing) → body + per-VS framing | grounding rule (every claim traces to a phrase) |
| Business Needs | **LLM ×N** | raw + VS + selected stages → Business Needs text | 1 call per VS; one block per stage |
| Capabilities (L3) | **LLM ×N** | raw + VS + per-stage candidate L3 → L3 per stage | 1 call per VS; stage isolation + salvage |
| Assembly (L2, title, package) | no | generated parts → Theme package per VS | L2 = unique parent of L3; title = template |

**4. Cost line:**
> *Per new ticket: **5 + 2N LLM calls** (+1 embedding); retrieval, catalogue load, L2, salvage, title and
> assembly use no generation call. Wall-clock ≈ 27s end-to-end, excluding the HITL gate.*

**5. (Optional) pointer line** to where the detail lives:
> *Phase A storage shapes are in §4; runtime selection in §5; theme generation in §6; measured quality
> per stage in §7 / the EDA documents.*

---

## Consistency notes
- Condense = **×1** (matches §5.1 locked design).
- VS retrieval = **summary** query; VS candidates = **all 50 from Azure SQL** (not the index) — matches
  the reworked §5.
- Theme-gen = **3 + 2N** in §6 wording; the **5 + 2N** here is the whole pipeline (adds Condense + VS
  Selection). Both correct; don't reconcile to one number.
- Stage metrics if cited = recall-first **F1 ~0.50 / recall ~0.89** (matches §7).

## Checklist
- [ ] §1.2 "End-to-end flow" added after §1.1 (or end of §1).
- [ ] Phase A + Phase B stage tables present (one row per stage, LLM/no-LLM marked).
- [ ] `5 + 2N` cost line added.
- [ ] Figure referenced (Figure 0 / `master_flow.png`).
- [ ] No contradiction with §4/§5/§6/§7 (see consistency notes).
