# TDD update instructions (v9 → v10) — for the coworker editing the doc

**Do not change anything else.** Apply exactly the edits below to `tdd_updated_v9.docx`, save as
`tdd_updated_v10.docx`. The doc is out of sync with the shipped code in five areas:

1. Historic **direct/implied classification was removed** end-to-end (ingestion, Cosmos + index
   schema, retrieval, ranking, candidate blocks).
2. The **historical retrieval lane is now hybrid (BM25+vector) + semantic reranking**, not pure
   vector.
3. A **data-driven generic-stream penalty** was added to ranking.
4. **All LLM calls now use strict structured output** (the pydantic schema is enforced).
5. **Theme generation was re-architected to batch calls** (description body + batched framing,
   one batched stage call for all VS, one capability call per VS), and **`stageScope` was removed**.

Work in two passes: **(A)** rebuild the three diagrams in Figma first, **(B)** then apply the
text edits. Diagrams come first because several sections reference them.

---

# PART A — Diagrams (build these in Figma, export PNG, replace the existing figures)

Use Figma. Create one FigJam/flow board per figure, simple boxes + arrows, left-to-right or
top-to-bottom. Keep the existing visual style (rounded boxes, light fills). Export each at 2x PNG
and replace the matching image in the doc. The three figures map to the three `[IMAGE]` spots:
Figure 1 (§3), Figure 2/2a (§5), Figure 3 (§6).

## Figure 1 — Ingestion flow (UPDATE: remove the classification step)

Boxes and arrows, top-to-bottom, two swimlanes:

**Lane 1 — Historic ER ingestion (nightly batch)**
```
iTech DB audit
  (eligible ERs after 2023-01-01, Theme links present, issue type = ER,
   keep only valid/partially-valid approved VS ground truth)
        ↓
Jira API fetch  (description, attachments, linked Themes/GROUPs)
        ↓
Attachment extraction  (idea-card priority: PPT/PPTX → PDF → DOC/DOCX, top 4; cap context)
        ↓
Condense (single LLM pass)  →  summaryFields + generationSignals
        ↓
Value Stream resolution  (each Theme summary → approved 50-VS catalogue; fuzzy + LLM confirm;
                          drop Themes that don't resolve)
        ↓
Build documents:
   • Cosmos IDMT/ER doc  (properties + themes[] ground truth = id + name only)
   • Cosmos Theme docs   (one per linked GROUP)
   • Historical index doc (content + content_vector, embedded)
        ↓
Persist:  Cosmos (system of record)   +   idp_teg_data  (AI Search, EngagementRequest lane)
```

**Lane 2 — Value Stream catalogue ingestion**
```
Sightline catalogue  →  dedupe / organize / tag  →
   Cosmos catalogue doc (VS → stages → L3/L2/L1)   +   idp_teg_data (ValueStream lane, embedded)
```

> **What changed vs the old Figure 1:** DELETE the "direct/implied classification" box/step that
> sat after VS resolution. The themes[] ground truth now carries only `valueStreamId` +
> `valueStreamName` (no supportType/reason/evidence). Nothing else in this figure changes.

## Figure 2 — Data science / Value Stream selection flow (UPDATE: lane method + ranking)

Top-to-bottom:
```
IDMT ticket id
        ↓
Condense  →  summaryFields (retrieval + LLM context) + generationSignals
        ↓
Two retrieval lanes on idp_teg_data, IN PARALLEL:
   ┌─────────────────────────────────────────────┬─────────────────────────────────────────────┐
   │ Value Stream catalogue lane                  │ Historical Engagement Request lane           │
   │ entityType = ValueStream                     │ entityType = EngagementRequest               │
   │ Hybrid (BM25 + vector) + semantic reranker   │ Hybrid (BM25 + vector) + semantic reranker   │
   │ → top 50 VS candidates                       │ → top 6 historical tickets (shown to SME)    │
   └─────────────────────────────────────────────┴─────────────────────────────────────────────┘
        ↓
Candidate merge → 3 lanes: semantic_plus_historic | historic_only | semantic_only
        ↓
Ranking:
   • semantic (reranker) score
   • historical evidence: co-occurrence frequency + best/weighted support score
   • GENERIC-STREAM PENALTY (new): demote broad/high-false-positive-rate streams
     UNLESS earned by historical evidence (≥3 supporting tickets)
   • validation against the approved 50-VS registry
        ↓
Review pool (window = 18; greedy backfill so it's never starved)
        ↓
Single selection LLM call  (strict structured output)
        ↓
Exactly N value streams (default 10)  →  ranked recommendations
        ↓
HITL approval (SME confirms the final VS set)
```

> **What changed vs the old Figure 2:** (1) the **historical lane** label was "Vector similarity
> over content_vector" — change it to **"Hybrid (BM25 + vector) + semantic reranker"** (same as the
> VS lane). (2) In the **Ranking** box, REMOVE "support type" and "reason/snippet"; ADD the
> **generic-stream penalty** bullet. (3) Add **"strict structured output"** on the selection LLM box.

## Figure 3 — Theme generation flow (BIG REDESIGN: batched architecture)

This is the most changed figure. The old one showed per-VS "Stage prediction ‖ Theme description"
fanning out for every VS. The new architecture splits work into **ticket-level (done once for all
approved VS)** and **per-VS**. Draw it as two bands.

```
HITL approval of N approved value streams
        │
        ▼
┌──────────────────────── TICKET-LEVEL  (once for ALL approved VS, 3 calls in parallel) ─────────────────────┐
│                                                                                                            │
│   Description BODY                Description FRAMING                 Stage selection                       │
│   (shared, VS-agnostic;           (ONE batched call for all VS;       (ONE batched call for all VS;         │
│    availability + initiative      one opening paragraph per VS)        each VS picks from its own            │
│    + capabilities sections)                                            governed candidate stages)           │
│   → 1 call                        → 1 call                            → 1 call → {vs_id: selectedStages}     │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
        │  (assemble per VS: theme description = "Theme Description:" + framing[vs] + shared body)
        ▼
┌──────────────────────── PER APPROVED VS  (fan out across VS, 2 calls each in parallel) ─────────────────────┐
│                                                                                                            │
│   Business Needs                                  Capabilities                                             │
│   (per VS, over its selected stages;              (ONE call per VS covering ALL its selected stages;       │
│    grouped Value Stage → feature → needs)          per stage pick L3 from that stage's candidates;         │
│   → 1 call / VS                                    L2 derived 1-1 from selected L3, no LLM call)            │
│                                                   → 1 call / VS                                            │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
Assemble Theme package per VS:
   deterministic title ("<ticket title> - <VS name>") + description + selected stages
   + Business Needs + L2/L3 capabilities
        ▼
Theme packages → SME review
```

> **What changed vs the old Figure 3:**
> - Theme **description** is no longer one full call per VS. It is a **shared body (1 call)** + a
>   **batched framing call for all VS (1 call)**, assembled per VS.
> - **Stage selection** is no longer per VS — it is **one batched call for all VS**.
> - These three (body, framing, stages) are **ticket-level, run once, in parallel**.
> - **Capabilities** is no longer one call per stage — it is **one batched call per VS** covering
>   all that VS's stages.
> - **Business Needs** stays per VS (it is the only generator that must stay per VS — its content
>   is organized entirely around each VS's own selected stages, with no shareable part).
> - Net call count for N=10 VS / ~3 stages each: **~60 → ~23** LLM calls.

---

# PART B — Text edits, section by section

## §2 Source of Truth and Data Ownership (table, "Engagement Request (ER)" row)
**FIND** (Extraction / Processing cell):
> "... Extraction, LLM summary, VS fuzzy match and direct/implied classification enrich the record."

**REPLACE WITH:**
> "... Extraction, LLM summary, and VS fuzzy match (with LLM confirmation) enrich the record.
> Theme ground truth stores the resolved Value Stream id and name only."

## §4.3 Cosmos properties.themes array object
**DELETE these three table rows entirely:** `supportType`, `reason`, `evidence`.
The themes[] object now has only: `key`, `groupId`, `valueStreamId`, `valueStreamName`.

In the **Example — Cosmos IDMT/ER document** JSON, change the themes entry from:
```json
"themes": [ { "key": "3966046", "groupId": "GROUP-23618",
  "valueStreamId": "VSR00074590", "valueStreamName": "Resolve Appeal",
  "supportType": "direct", "reason": "...", "evidence": "..." } ]
```
**TO:**
```json
"themes": [ { "key": "3966046", "groupId": "GROUP-23618",
  "valueStreamId": "VSR00074590", "valueStreamName": "Resolve Appeal" } ]
```

## §4 (idp_teg_data index — historical document, if a valueStreams[] sub-table or example is shown)
Wherever the **historical index document's `properties.valueStreams[]`** is described, it now has
only `valueStreamId` and `valueStreamName`. Remove any `supportType` / `reason` / `evidence`
sub-fields there too. (Add a one-line note: "historic VS labels carry id + name only; support
classification was removed — see §5.4 rationale.")

## §5.3 Unified index retrieval lanes (table)
In the **Historical Engagement Request lane** row, the "Retrieval method" cell currently says:
> "Vector similarity over content_vector for curated historical ticket context"

**REPLACE WITH:**
> "Hybrid (BM25 + vector) + semantic reranker over content/content_vector — the same retrieval
> method as the catalogue lane. The semantic reranker score (0–4) is normalized to 0–1 to match
> the candidate-ranking scale."

(The Value Stream catalogue lane row is already "Hybrid search …" — append "+ semantic reranker"
to it for accuracy.)

## §5.4 Candidate merge, ranking and review pool
1. In the **Historic-only** row ("Ranking treatment" cell), FIND:
   > "Included when historical evidence, support type, reason/snippet, or frequency across selected
   > tickets is strong."
   **REPLACE WITH:**
   > "Included when historical evidence is strong — co-occurrence frequency and best/weighted
   > support score across the selected tickets."

2. In the paragraph below the table, FIND the final sentence:
   > "Ranking uses lane, catalogue score, historical-ticket score, selected-ticket evidence,
   > support type, frequency across selected examples, and validation against the approved Value
   > Stream registry."
   **REPLACE WITH:**
   > "Ranking uses lane, catalogue (reranker) score, historical-ticket score, co-occurrence
   > frequency across the selected examples, a data-driven generic-stream penalty, and validation
   > against the approved Value Stream registry."

3. **ADD a new short paragraph** after that (new sub-point or inline):
   > "**Generic-stream penalty.** A small number of broad value streams (e.g. broad strategy,
   > operations, or analytics streams) match many ideas semantically and crowd out stream-specific
   > candidates. Each stream carries a corpus-derived false-positive-rate prior (how often it is
   > predicted but is not ground truth); high-prior streams are demoted in ranking UNLESS they are
   > earned by historical evidence (at least three supporting historical tickets). The penalty
   > applies to ranking only — it never hard-excludes a stream, and the LLM still makes the final
   > selection. No stream names are hard-coded; the prior is derived from data."

4. **Rationale note** (add wherever §5.4 or §2 mentions the old classification): "Historic
   direct/implied classification was removed after an offline evaluation showed it did not improve
   selection relevance and slightly reduced it; the historic lane now contributes pure
   co-occurrence + frequency + similarity evidence."

## §5.5 LLM selection prompt and output
1. **Candidate block format** — the example block currently shows:
   > `historical: tickets=2 (direct=1, implied=1), best=0.82, weighted=1.0, ids=[IDMT-####]`
   > `evidence: <snippet from a prior ticket>`
   **REPLACE the historical line WITH** (and DELETE the evidence line):
   > `historical: tickets=2, best=0.82, avg=0.77, weighted=1.0, ids=[IDMT-####]`

2. **Expected LLM output** — keep `supportType: direct or implied` and `reason` (these are the
   selection LLM's own labels for its picks — they are NOT the removed historic classification).
   Change the "source tickets" bullet to:
   > "source tickets: included only for **implied** picks (a direct pick is named by the idea card
   > and needs no historic backing)."

3. **ADD a sentence** to "Selection and execution behavior":
   > "All LLM calls in the solution use strict structured output: the response schema (a typed
   > model) is enforced by the gateway, so the model cannot omit, rename, or wrap fields."

4. The exact-count sentence stays as-is ("exactly the requested count (default 10): trimmed or
   padded"). Confirmed product behavior — do NOT change it.

## §6.1 Orchestration sequence  (REWRITE the bullet list)
Replace the current bullets with the batched architecture. New bullets:

> The sequence is approval-gated: nothing is generated until the SME confirms the Value Stream set.
> After approval, generation is split into **ticket-level work done once for all approved Value
> Streams** and **per-Value-Stream work**.
>
> **Ticket-level (one set of calls for all approved VS, run in parallel):**
> - **Theme Description — shared body:** one call produces the VS-agnostic body (Product
>   Availability, initiative overview, digital/operational capabilities) from the ticket signals.
>   It is reused under every Theme.
> - **Theme Description — framing:** one batched call produces the VS-specific opening paragraph
>   for every approved Value Stream at once. Each Theme's description is `"Theme Description:"` +
>   its framing paragraph + the shared body.
> - **Stage selection:** one batched call selects stages for every approved Value Stream at once;
>   each VS is matched only against its own governed candidate stages, and the result is keyed by
>   value stream id.
>
> **Per approved Value Stream (fan out across VS, two calls each in parallel, after stages):**
> - **Business Needs:** one call per VS over that VS's selected stages.
> - **Capabilities:** one call per VS covering all of that VS's selected stages; for each stage the
>   LLM picks applicable L3 capabilities from that stage's governed candidate L3 list (never
>   invents, never borrows another stage's capability). Each selected L3 maps 1-1 to its parent L2,
>   so the L2 set is derived deterministically — no separate L2 call.
> - **Theme title:** deterministic — IDMT ticket title + approved Value Stream name.
>
> Net effect: theme description is 2 calls total (not one per VS), stage selection is 1 call total
> (not one per VS), and capabilities is one call per VS (not one per stage).

## §6.2 Context passed to each generation call
1. **Stage Prediction → Output:** FIND:
   > "A stage scope (specific_stages | entire_value_stream | broad_or_unclear) decides whether
   > specific stages are listed or the whole value stream is taken; only governed catalogue stages
   > are returned."
   **REPLACE WITH:**
   > "Output is `selectedStages` per VS, each `{stageId, stageName, reason}`, resolved only against
   > that VS's governed stages (invented or cross-VS ids are dropped). There is no scope flag: an
   > approved Value Stream is never left empty — if the model returns no usable stages, the full
   > governed stage list is taken for the architect to trim. A stage with a reason was predicted;
   > an empty reason means it came from the full-list fallback."

   Also change the **Stage Prediction context** header note: it is now part of **one batched call
   for all approved VS** (each VS supplies its own value stream + governed stages), not a per-VS
   call.

2. **Theme Description** — split the context into the two calls:
   > "**Body call (shared, once):** ticket context (summaryFields) + generationSignals
   > [marketSegments, fundingModelSignals, marketOpportunity, businessSolutionObjectives,
   > valueProposition, estimatedBenefits, dependencies, resourcesNeeded, digitalExperienceSignals,
   > productAvailabilitySignals, planSignals, networkSignals, productPairingSignals,
   > operationalSignals, reportingSignals, notes]. No value stream input.
   > **Framing call (batched, once):** ticket context + the list of approved value streams
   > (valueStreamId, valueStreamName, valueStreamDescription, valueProposition). Output: one opening
   > paragraph per value stream."
   Also update the Output paragraph: the description opens with a `"Theme Description:"` heading,
   then the framing paragraph, then the shared Product Availability / initiative / capabilities
   body. Product Availability values are still copied from signals only, never invented; clarify
   that **Funding Model = insurance funding model (ASO / FI / Commercial), not project/seed
   funding**, and **Plans = states/markets, not benefit features** (these were a correctness fix).

3. **Capabilities** — update to: "one batched call per Value Stream covering all its selected
   stages; selection is biased toward precision (exclude by default; pick a capability only when a
   specific idea-card phrase requires it within that stage — typically 1–3 per stage)."

## §6.3 Final Theme Package
Confirm the description field is the assembled `"Theme Description:" + framing + body` string, and
that selectedStages entries are `{stageId, stageName, reason}` (no scope, no rank, no evidence).
No structural change otherwise.

---

# Summary of every removal (quick checklist for the editor)
- [ ] §2: drop "direct/implied classification" from the ER processing description
- [ ] §4.3: delete `supportType`, `reason`, `evidence` rows + from the example JSON
- [ ] §4 historical index doc: drop the same three sub-fields from valueStreams[]
- [ ] §5.3: historical lane → "Hybrid + semantic reranker" (not pure vector)
- [ ] §5.4: remove support-type/snippet from ranking; ADD generic-stream penalty + rationale
- [ ] §5.5: candidate block drops `(direct=, implied=)` and the `evidence:` line; source tickets =
      implied-only; add strict-structured-output note
- [ ] §6.1: rewrite orchestration to the batched architecture (ticket-level vs per-VS)
- [ ] §6.2: remove `stageScope`; add never-empty fallback; split Theme Description into body +
      framing; capabilities = per-VS batched + precision bias; Funding Model / Plans correctness note
- [ ] Figures 1, 2, 3 rebuilt in Figma and replaced
