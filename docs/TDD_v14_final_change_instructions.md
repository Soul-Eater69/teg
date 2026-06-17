# TDD change instructions → next version

**For:** the coworker maintaining the TDD.
**Input file:** the **latest** TDD (`tdd_updated_v15.docx`) · **save as:** the next version.

> **Already applied in v15 (no-op — skip if already done):** buckets/lanes removed, "up to 8
> attachments", Contract B `rawText`, retrieval rework text, `latencyMs: 15000`. Apply only what's still
> outstanding below.

> **TEXT vs FIGURES — important:** a text-editing LLM can do all the prose/table/contract edits, but it
> **cannot re-render the figures** (Figures 1–3 are Figma images). Every "re-render / re-draw" item
> below must go to whoever owns the Figma file — list those out separately for them. Text edits the LLM
> *can* do: Parts 1 (text bits), 3, 6, 7, 8, 9.

Scope = **§5 Data Science**, **§6 Theme Generation**, **§7 Evaluation**, and **Figures 1–3**.

---

## Part 1 — §5 text fixes

### 1a. §5.2 — "top four" → "up to 8" attachments  (CONTRADICTION)
§5.2 currently reads: *"…the fallback path summarizes the IDMT ticket description and extracts the
**top four** supported attachments using the ingestion priority order: PPT/PPTX, PDF, then DOC/DOCX."*

Every other place (§3, §5.1, Figure 1) says **up to 8**. Change "top four" → **"up to 8"**:
> *"…the fallback path summarizes the IDMT ticket description and extracts **up to 8** supported
> attachments using the ingestion priority order: PPT/PPTX, PDF, then DOC/DOCX."*

### 1b. Retrieval & VS-candidate rework (§5.3–§5.5)  — REPLACES the two-lane / bucket model

**This is the big one.** The current §5.3–§5.5 describe a two-lane retrieval (a "VS Catalogue lane"
that semantically retrieves Value Streams from the index) merged into **three buckets**
(semantic_plus_historic / historic_only / semantic_only) with a generic-stream penalty and a windowed
review pool. **None of that is the locked design** (it's the legacy `topk` mode; the winning config is
the `evidence`/all-50 mode — see `docs/vs_representation_eda.md`). The real flow is:

- **Value Streams are NOT in the index.** The `idp_teg_data` index holds **only historical
  Engagement-Request documents**. There is **no VS-catalogue retrieval lane**.
- **All 50 approved Value Streams come from the Azure SQL DB** (the org's gold catalogue — *integration
  not yet wired up*). The **entire 50-VS set** is passed to the selection LLM; nothing is
  retrieved/ranked/trimmed to produce VS candidates.
- **Retrieval = one lane only:** embed the **new ticket's summary** (~460 tok) → return the **top 6
  similar historical ER tickets** from the index (shown to the SME), each carrying its VS ground-truth
  labels.
- **No candidate merge, no buckets/lanes, no generic-stream penalty, no review-pool window.** Delete
  all of it.
- **The selection LLM prompt reads:** the new ticket's **raw idea-card text** (~24k tok) + the **full
  50-VS catalogue** + the **6 historical tickets as summaries** (with their VS labels). It returns the
  picks (default 10). *(Per the EDA: raw new-ticket text is the lever, +0.071 F1; historic shown as
  summaries; summary is the retrieval query only.)*

Concretely, rewrite the three subsections:

**§5.3 "Unified index retrieval lanes" → "Historical ticket retrieval".** Replace with: *"The new
ticket's summary is embedded and used to retrieve the top 6 most similar historical Engagement-Request
documents from `idp_teg_data` (the index holds only historical ER documents; it is retrieval-only,
returning ranked ids whose ticket summary + resolved VS ground-truth are read from Cosmos). The 50
approved Value Streams are NOT retrieved — the full governed set is supplied from the Azure SQL DB
(integration pending) and passed in whole to the selection step."* Delete the two-lane table; keep only
the historical-retrieval description.

**§5.4 "Candidate merge, ranking and review pool" → DELETE the bucket/merge/penalty machinery.** Remove:
the three-lane merge, the semantic_plus_historic / historic_only / semantic_only definitions and table,
the generic-stream penalty paragraph, and the windowed review pool. (The "direct/implied classification
removed" note can stay or move to §5.2 — it's an ingestion fact.) Replace with one short paragraph:
*"There is no candidate trimming: all 50 approved Value Streams are presented to the selection LLM,
with the 6 retrieved historical tickets as precedent evidence. The model — not a pre-ranking step —
decides relevance."*

**§5.5 "LLM selection prompt and output".** Fix the prompt inputs: the new-ticket context is the
**raw idea-card text (~24k tok)**, *not* the summary fields (the summary is only the retrieval query).
Remove "curated review pool built from both retrieval lanes" and the "candidate blocks grouped into …
lanes" language. The prompt = **raw new-ticket text + the 50-VS catalogue + 6 historical summaries**.
Output (valueStreamId/Name, confidence, supportType, reason, sourceTickets for implied) is unchanged.

**§5.5 "Candidate block format".** Each VS candidate's compact block should **add the Value Stream's
`assumptions`** (from the catalogue) and **drop the `lane:` line** (no more lanes; the evidence mode
runs with `show_scores=False`, so no `lane` / `semantic` / `historical` score lines appear). Resulting
block — one per Value Stream, all 50 passed in:
> ```
> Candidate: Configure, Price and Quote
> entity_id: VSR-####
> description: <value stream description>
> category: Sales and Enrollment
> trigger: <what initiates the value stream>
> value: <value proposition>
> assumptions: <value stream assumptions>
> ```
> (Also fix the duplicated heading "Candidate block format **format**" → "Candidate block format".)

**§5.5 "Selection and execution behavior".** Remove the bullets that reference **lanes** ("Candidates
appearing in **both lanes** are prioritized…", "Historic-only candidates…", "Semantic-only
candidates…"). There are no lanes. Replace with: *"All 50 Value Streams are presented together; the LLM
weighs each one's catalogue fit against the similar past tickets (below) and the new ticket's raw
text — there is no pre-ranking or lane priority."*

**§5.5 — ADD the historic ticket (evidence) block format.** Separate from the candidate blocks, the 6
retrieved similar tickets are passed as their own labelled block (this is the `evidence` mode's
`_render_evidence`, `historic_repr = "summary"`): each ticket = its **summary** + the **VS it was
tagged with**:
> ```
> SIMILAR PAST TICKETS (evidence — the value streams these were tagged with):
> - IDMT-17432: <that ticket's summary text>
>   -> tagged value streams: Configure, Price and Quote (VSR-0042), Order Management (VSR-0017)
> - IDMT-16890: <that ticket's summary text>
>   -> tagged value streams: Resolve Appeal (VSR-0074)
> ```
> So the selection prompt has two parts: (1) the **50 candidate blocks** (the choices), and (2) this
> **SIMILAR PAST TICKETS** evidence block (precedent — each shown as its summary + tagged VS labels),
> plus the new ticket's raw idea-card text. The historic tickets are shown as **summaries**, not raw.

**Contract B — Request.** It currently sends only `summaryFields`. Add the new ticket's **`rawText`**
(that's what the selection LLM reads); `summaryFields` stays as the retrieval/embedding query. Remove
any bucket/lane fields if present.

**Contract B — Response.** **Remove the top-level `historicalTickets[]` array.** Each recommendation
already carries its `sourceTickets` (for implied picks), so the historical evidence is attached per-VS;
the separate historical block is redundant in the response. Keep `recommendations[]`, `model`,
`latencyMs`.

### 1b-note. Stage / L2 / L3 catalogue source (§6) → **Azure SQL DB**
Same gold-data move applies to the stage and capability catalogues used in §6:

| location | current | change to |
|---|---|---|
| §6 intro | *"…governed catalogue data **from Cosmos**."* | *"…governed catalogue data **from the Azure SQL DB**."* |
| §6.2 Stage Selection, 2nd bullet | *"…governed candidate stages from the **Cosmos catalogue**…"* | *"…governed candidate stages from the **Azure SQL catalogue**…"* |

(Cosmos still holds historical IDMT/Theme documents + ground truth — don't change those references.)

### 1c. (minor) §5.1 — drop the dead field name
§5.1 says raw text is read *"not summaryFields or **generationSignals**"*. `generationSignals` no longer
exists. Either drop "or generationSignals" or leave it; low priority.

---

## Part 2 — Figure fixes

### 2a. Figure 1 (Ingestion & Condense)
- **Remove `themes[]`** from the "Cosmos IDMT/ER Document" box's `properties { … }` list. (Themes are
  separate Theme documents found via `parentRef`, not embedded — matches §4.2.)
- **Add `domain`** to that box's top-level field list (`id, key, sourceId, source, entityType, domain,
  createdAt/By, lastModifiedAt/By, parentRef, properties`). `domain = "WORKITEM"`.

### 2b. Figure 2 (Value Stream Prediction) — re-draw the retrieval/merge section
The current Figure 2 draws the legacy two-lane / bucket model and must be **redrawn** to the locked flow
(the dashed note box at the bottom is already correct — make the boxes above it agree):

- **Delete the "VS Catalogue Lane" box** (the one retrieving `entityType = ValueStream` from the index).
  Value Streams are not in the index.
- **Delete "Candidate Merge (3 lanes: semantic_plus_historic | historic_only | semantic_only)".** No buckets.
- **Delete the "Ranking" box** (semantic reranker score / generic-stream penalty / lane validation) and
  the "Review Pool (window = 18)" box. No pre-LLM ranking or trimming.
- **Keep one retrieval box:** *"Embed new ticket summary → top 6 similar historical ER tickets from
  idp_teg_data (historic docs only; VS ground-truth + summary read from Cosmos)."*
- **Add a catalogue box:** *"50 approved Value Streams — Azure SQL DB (gold catalogue; integration
  pending)."* feeding straight into selection.
- **LLM VS Selection** box: *"single call — reads new ticket RAW text + all 50 Value Streams + 6
  historical tickets (as summaries) → scored, ranked recommendations."*
- Then **ValueStreamResponse → HITL approval** as today.

So the corrected vertical flow is:
`IDMT Ticket ID → Condense → [embed summary → top-6 historical tickets]  +  [50 VS from Azure SQL]
→ LLM VS Selection (raw text + 50 VS + 6 summaries) → ValueStreamResponse → HITL approval.`

(Both figures are images — they must be **re-rendered**, not text-edited.)

---

## Part 3 — Metric numbers (§5.6 prose + §7 table must agree)

### 3a. Stage selection → use the **recall-first (no count cap)** config
Lock stage metrics to the recall-first operating point (no count cap), and make §5.6 and the §7 table
report the **same** numbers:

- **precision ≈ 0.35  ·  recall ≈ 0.89  ·  F1 ≈ 0.50**

**§5.6 "Stage selection quality metrics"** — replace with:
> *Precision is monitored on the selected stages against approved stage ground truth; observed ≈ **35%**.
> Recall is monitored against the same ground truth; observed ≈ **89%**. The stage selector runs with
> **no count cap** (recall-first): it returns every stage the work plausibly touches and the architect
> trims, so recall is prioritised and precision is intentionally lower (the thin, under-tagged ground
> truth also understates true precision).*

**§7 locked-results table, Stage selection row** — replace:
> `Stage selection | F1 / recall (answerable stages, one_call) | ~0.48 / ~0.54`

with:
> `Stage selection | F1 / recall / precision (answerable, one_call, no count cap) | ~0.50 / ~0.89 / ~0.35`

### 3b. Value Stream — label the operating point so §5.6 and §7 don't look contradictory
§5.6 reports VS **precision 60–65% / recall 75–82%** (the count=10 operating point); the §7 table
reports **F1 ~0.78 (= P = R at count = ground truth)**. Both are correct but at different operating
points. Add one clause to §5.6 so they reconcile:
> *"…(measured at the default requested count of 10; at count = ground truth, precision = recall = F1
> ≈ 0.78 — see §7)."*

---

## Part 4 — Fix misleading example latencies

Replace the placeholder `latencyMs` values in the contract examples with the measured numbers:

- **§5.5 Contract B — Response:** `"latencyMs": 34200` → **`5200`** (VS selection ≈ 5.2s, single call).
- **§6.3 Contract C — Response:** `"latencyMs": 48700` → **`15000`** (theme generation ≈ 15s wall-clock
  with the parallel 3 + 2N fan-out; the 48.7s figure was a sequential, pre-parallel estimate).

---

## Part 5 — §7.4 Cost: add the measured table

§7.4 currently describes cost reporting but has no numbers. Add this table (measured: 25 tickets, raw
text only, sequential per-call so the gateway isn't queueing). Latency unit is per ticket (stages,
description) or per Value Stream (L3, business needs); tokens are per LLM call.

| component | avg lat | median | max | avg prompt tok | avg completion tok |
|---|---:|---:|---:|---:|---:|
| Stage selection | 7.1s | 3.7s | 25.5s | 7,602 | 1,273 |
| Theme Description (body+framing) | 6.0s | 5.7s | 10.1s | 5,152 | 853 |
| L3 capability | 4.3s | 3.9s | 9.2s | 5,847 | 699 |
| Business Needs | 8.3s | 7.8s | 17.0s | 5,520 | 1,567 |

Add below the table:
> *With the parallel 3 + 2N fan-out, theme generation completes in **~15s wall-clock** regardless of the
> number of approved Value Streams (the per-VS calls run concurrently). End-to-end model time is
> **~27s** (condense ~7s + Value Stream retrieval/selection ~5s + theme generation ~15s), excluding the
> human approval gate. Business Needs is the slowest component because it emits the most tokens (~1,567
> completion), not from any sequential sub-call.*

---

## Part 6 — Remove the verbose JSON contract blocks

The big illustrative JSON request/response examples are not needed in the TDD — they clutter the
document. **Remove the JSON code blocks** for:
- **Contract A** — Request + Response (§5.1)
- **Contract B** — Request + Response (§5.5)
- **Contract C** — Request + Response "Full Package" (§6.3) — this is the largest (~60 lines)
- The **`// Per-call slice outputs (6.2)`** comment block (§6.3)

Replace each removed block with a **compact field list** so the API contract is still recorded without
the fake-data JSON. For example, Contract C becomes:
> *Request: `ticketId, ticketTitle, condensed.rawText, approvedValueStreams[{valueStreamId, valueStreamName}]`.
> Response: `themePackages[]`, each `{ valueStreamId, valueStreamName, themeTitle, themeDescription,
> selectedStages[{stageId, stageName, reason}], businessNeeds, l2Capabilities[ per stage ],
> l3Capabilities[ per stage {capabilityId, name, reason} ] }`, plus `model, promptVersion, latencyMs`.*

(If you'd rather drop the contracts entirely, that's fine too — but keep at least the one-line field
list so the request/response shape isn't lost.)

## Part 7 — Reformat §5 (DS solution) input/output and text

§5.5's prompt inputs / candidate block / expected output are run together and read poorly. Reformat into
three clean labelled blocks:

- **Prompt inputs** (bullet list): new ticket **raw idea-card text (~24k tok)**; the **full 50-VS
  catalogue** (each: name, description, category, trigger, value proposition, assumptions); the **6
  historical ER tickets as summaries** with their VS ground-truth labels; **user count control**
  (default 10, count-only custom instruction).
- **Candidate block format** (fix the duplicated heading "Candidate block format **format**" → single
  heading) — show the block once (with `assumptions`, no `lane:` — Part 1b).
- **Expected output** (bullet list): `valueStreamId, valueStreamName, confidence (0-100), supportType
  (direct|implied), reason, sourceTickets (implied only)`; output is exactly the requested count.

Remove any leftover run-on/duplicate paragraphs (e.g. the "Prompt inputs passed to the LLM" line
followed by a second "Prompt inputs:" line — keep one).

## Part 8 — Two §6.2 parity fixes (minor)

- **Capabilities context** (§6.2) lists only `valueStreamId, valueStreamName`. Add
  **`valueStreamDescription`** for parity with the Business Needs context (the code passes it).
- **Capability field name:** Contract C uses `"name"` for capabilities; confirm the final response model
  emits `name` (not `capabilityName`) so the contract matches the serializer. If it emits
  `capabilityName`, update the contract field list to match.

## Part 9 — Remove the "60 → 23 calls" comparison

Drop the "previous architecture" call-count comparison everywhere it appears — keep only the plain
`3 + 2N` call structure:
- **§6.1 "Net effect" paragraph:** remove *"compared with the previous architecture's roughly 6 calls
  per Value Stream (~6N). For N = 10 … reduces the call count from roughly 60 to roughly 23."* Keep the
  sentence up to "…for **3 + 2N** calls overall." (end it there).
- **Figure 3** bottom note box: remove the *"Net effect for N = 10: ~60 LLM calls → ~23 LLM calls"* box
  (re-render).
- **§7.4 Cost:** it states "approximately 23 LLM calls for a ticket with 10 approved Value Streams" — no
  "60" comparison there, so that plain count can stay; just ensure no "60 →" phrasing remains.

## Verification checklist before saving v15

- [ ] §5.2 says "up to 8" attachments (no "top four" anywhere). Search doc for "four" → 0 stray hits.
- [ ] §5.3–5.5 reworked: **no VS retrieval lane** (VS not in index), **no buckets/lanes**, **no
      generic-stream penalty**, **no review-pool window**. Search doc for `semantic_plus_historic`,
      `historic_only`, `semantic_only`, `generic-stream`, `review pool`, `Candidate Merge` → 0 hits.
- [ ] §5.3 = single historical-retrieval lane (top-6 ER tickets); 50 VS supplied from **Azure SQL DB**
      (integration pending) and passed in whole.
- [ ] §5.5 prompt input = new ticket **raw text** (not summary fields); Contract B request includes `rawText`.
- [ ] §5.5 candidate block adds `assumptions`, drops `lane:`; heading "Candidate block format" (not "…format format").
- [ ] §5.5 "Selection and execution behavior" has no "lane" bullets; replaced with the all-50 sentence.
- [ ] §5.5 includes the **SIMILAR PAST TICKETS** evidence block format (per ticket: summary + tagged VS).
- [ ] Contract B **response** has no top-level `historicalTickets[]` (recommendations + `sourceTickets` only).
- [ ] JSON contract blocks (Contract A/B/C request+response + slice-outputs comment) removed; replaced
      with compact field lists.
- [ ] §5.5 reformatted into clean Prompt inputs / Candidate block / Expected output blocks; no
      duplicated headings or run-on "Prompt inputs" lines.
- [ ] §6.2 Capabilities context adds `valueStreamDescription`; capability field name confirmed (`name`).
- [ ] "60 → 23 calls" comparison removed from §6.1 + Figure 3; only `3 + 2N` remains.
- [ ] §6 intro + §6.2 Stage Selection catalogue source = **Azure SQL DB** (not Cosmos).
- [ ] Figure 1 re-rendered: `properties` has **no** `themes[]`, top-level has `domain`.
- [ ] Figure 2 re-drawn: no VS-catalogue lane / no merge / no ranking / no review pool; just
      [embed summary → top-6 historical] + [50 VS from Azure SQL] → LLM selection (raw + 50 VS + 6 summaries).
- [ ] §5.6 stage metrics = precision ≈35% / recall ≈89% (recall-first, no count cap); VS operating-point
      clause added.
- [ ] §7 table Stage row = F1 ~0.50 / recall ~0.89 / precision ~0.35.
- [ ] Contract B latencyMs = 5200; Contract C latencyMs = 15000.
- [ ] §7.4 has the measured cost table + the ~15s / ~27s note.
- [ ] Save as `tdd_updated_v15`.
