# TDD update instructions (→ final design) — for the coworker editing the doc

**Source file:** `tdd_updated_v11.docx`. Apply the edits below and save as the next version
(`tdd_updated_v12.docx`). If an edit is already reflected in your copy, skip it (note it as done).

This update brings the TDD in line with the **finalised, evaluation-validated design**. The prior
doc described generation as reading the condensed **summaryFields + generationSignals**; the final
design generates from the **raw idea-card text**, and several components changed based on offline
evaluation. The five big changes:

1. **All theme-generation calls read the RAW idea-card text** (~24k tokens), not summaryFields and
   not generationSignals. Summaries are used **only for retrieval** (finding similar past tickets),
   never for generation. ("Summary to find, raw to decide.")
2. **Stage selection and L3 capability selection drop the count cap** — they return *every* stage /
   capability the work exercises (no "typically 1–3" quota). This was the single largest recall
   lever in evaluation.
3. **Cross-element interlinking is prevented and corrected:** a strict-isolation prompt rule plus a
   deterministic **salvage** layer that reassigns a mislinked stage/capability to its true owner.
4. **The search index is retrieval-only:** historic docs store `searchText` + `content_vector` only;
   VS ground-truth labels and full content are fetched from **Cosmos by key**, and the 50 VS
   candidates come from the **catalogue file**, not the index.
5. **A new evaluation section** records how each component was measured and its locked numbers.

Work in two passes: **(A)** update the diagrams, **(B)** apply the text edits, then **(C)** add the
new evaluation section.

---

# PART A — Diagram updates

## Figure 2 — Value Stream selection flow (UPDATE: the input representation)
The "Condense → summaryFields" box feeds retrieval. ADD a note on the selection step that the
**new ticket's raw text is passed to the selection LLM prompt**, while the **summary is what is
embedded for retrieval**. One line under the selection box:
> "Retrieval embeds the summary; the selection prompt reads the new ticket's full raw text + the
> 50-VS catalogue + the 6 similar past tickets (shown as their summaries)."

Also: the **50 VS candidates come from the governed catalogue file**, and the historical lane
returns **ids only** — VS labels are enriched from Cosmos by key. Update the retrieval box note
accordingly ("index is retrieval-only: searchText + vector; VS labels from Cosmos / catalogue").

## Figure 3 — Theme generation flow (UPDATE: raw input + no count cap + salvage)
Keep the batched two-band architecture (ticket-level vs per-VS). Three labels change:
- Every generation box's input note changes from "summaryFields + generationSignals" to
  **"raw idea-card text (~24k tokens)"**.
- **Stage selection** and **Capabilities** boxes: change any "1–3 stages / capabilities" note to
  **"all that the work exercises — no count cap"**.
- Add a small **"salvage"** annotation on the batched Stage and Capability boxes: "a pick placed
  under the wrong value stream / stage is reassigned to its true owner (not dropped)."

---

# PART B — Text edits, section by section

## §6.2 Context passed to each generation call (the biggest rewrite)
The whole section currently passes **summaryFields + generationSignals** to each generator. Replace
that premise. Add a lead paragraph:

> **Generation input.** Every theme-generation call reads the **raw consolidated idea-card text**
> (the ticket description plus extracted attachment text, consolidated and capped to ~24,000 tokens
> at ingest). Generation does **not** use the condensed summary or the generation signals — those
> are produced for retrieval and routing only. The same raw text is the single factual source for
> the theme description, business needs, stage selection, and capability selection. (Rationale:
> evaluation showed the raw idea card gives generation the detail it needs; the summary is the right
> input for *retrieval*, not generation.)

Then, per generator:

1. **Theme Description (body + framing).** Both calls read the raw idea-card text (no signals).
   - The **body** prompt no longer "copies values from the matching signal." It now leads with a
     hard **grounding rule**: every statement must be supported by a specific phrase in the idea
     card; if it cannot be pointed to, it is omitted. Product Availability lines (Go-live, Plans,
     Market Segments, Funding Model, Networks) are included **only when the idea card explicitly
     states them** — never inferred. Funding Model = insurance funding (ASO / FI / Commercial), not
     project/seed funding; Plans = states/markets, not benefit features.
   - The **framing** prompt has the same grounding rule: no invented stakeholders, outcomes, or
     scope to fill a paragraph.

2. **Stage selection.** One batched call for all approved VS, reading the raw idea-card text. Each VS
   is matched only against its own governed candidate stages. **There is no count cap** — return
   every stage the work runs through, feeds, or changes (one or several). Output is `selectedStages`
   per VS (`{stageId, stageName, reason}`), resolved only against that VS's governed stages.
   **STRICT VALUE-STREAM ISOLATION:** candidate lists are disjoint; only ids printed under a VS may
   be returned for it; a stage placed under the wrong VS is **salvaged to its owning VS** by a
   deterministic post-step (a stage id belongs to exactly one VS) rather than dropped. An approved
   VS is never left empty: if no usable stages return, the full governed list is taken for the
   architect to trim. **Boundary handling:** when the work spans two adjacent stages, include both.

3. **Business Needs.** One call per VS over that VS's selected stages, reading the raw idea-card
   text. Same hard grounding rule (no invented need, note, dependency, rule, training, or reporting;
   the conditional sub-fields and Operational Training / Operational Reporting sections are included
   only when the card explicitly states them). The document is structured one `Value Stage:` block
   per selected stage; it must address every selected stage and keep each stage's needs within that
   stage's scope.

4. **Capabilities (L3 / L2).** One batched call per VS covering all its selected stages, reading the
   raw idea-card text. For each stage, select the L3 capabilities the work exercises from that
   stage's governed candidates. **There is no count cap** — include every capability the work runs
   through, feeds, or changes (operational reach counts, not only an explicit mention); when unsure
   between a clearly-relevant capability and omitting it, include it. **STRICT STAGE ISOLATION:**
   only ids printed under a stage may be returned for it; a capability placed under the wrong stage
   is **salvaged to its owning stage** (a capability id belongs to exactly one stage). Each selected
   L3 maps 1-1 to its parent L2, so the L2 set is derived deterministically — no separate L2 call.

> **Remove** the old §6.2 wording: "selection is biased toward precision (exclude by default; pick
> only when a specific phrase requires it; typically 1–3 per stage)." That precision/count framing
> was reversed — recovering the count-capped picks was the main recall improvement.

## §6.1 Orchestration sequence
Keep the batched structure. Update the input note in the lead paragraph: generation reads the
**raw idea-card text**, not the condensed summary/signals. Add one sentence at the end:

> "Each batched selection step (stages, capabilities) is followed by a deterministic salvage step
> that reassigns any cross-element mislink to its true owner; the strict-isolation prompt makes this
> rare, and the salvage guarantees a mislinked-but-valid pick is recovered rather than lost."

## §4 / §5 — Index and storage (retrieval-only index)
Wherever the **historical index document** is described, state it is **retrieval-only**: it stores
`searchText` (embedded as `content_vector`) plus the match key (`key` = IDMT-####) and `sourceId`.
It does **not** store `properties.valueStreams[]` or full content. Add:

> "Historic VS ground-truth labels and full ticket content live in Cosmos. When a similar past
> ticket is retrieved, its VS labels and content are fetched from Cosmos by key (one point-read
> returns both). The 50 governed Value Stream candidates come from the catalogue, not the index —
> the index holds only EngagementRequest retrieval documents."

(If a `valueStreams[]` sub-table or example is shown on the historic index doc, delete it.)

## §3 — Ingestion / condense (budget + idea-card-first)
In the condense / attachment-extraction description, state the consolidation budget and packing:

> "Attachment text is consolidated greedily to a ~24,000-token budget (idea-card source first, then
> ranked attachments until the budget is exhausted; up to 8 attachments are downloaded/extracted —
> the token budget, not a fixed count, caps the content). The consolidated raw text is the single
> input both to the condense summary pass (for retrieval) and to all downstream generation."

## §2 — Source of Truth (no change beyond the index note)
Cosmos remains the system of record; AI Search (`idp_teg_data`) is retrieval only. Add the
retrieval-only clarification from the §4/§5 edit if §2 references the index contents.

---

# PART C — NEW SECTION: Evaluation & validated performance

Add a new top-level section (e.g. **§7 Evaluation**) summarising how each component was measured and
its locked result. Keep it factual; full analyses live in the EDA documents.

> **Method.** Classification components (Value Stream, Stage, L3) are scored by precision / recall /
> F1 against Jira ground truth, reporting a **coverage ceiling** (how much ground truth is reachable
> from the governed catalogue) so a catalogue gap is not misread as a model error. Generative
> components (Theme Description, Business Needs) are evaluated **reference-free against the source**
> (the free-form ground-truth text is too varied to score against): **faithfulness** (claims
> grounded in the idea card), **hallucination** (`1 − faithfulness`), and **coverage** (source key
> facts reflected); Business Needs adds **stage usage** (every selected stage addressed) and
> **stage alignment** (needs in the right stage's scope).

> **Locked results** (evaluation cohorts; see the per-component EDA docs for detail):
>
> | component | metric | result |
> |---|---|---|
> | Value Stream selection | F1 (= P = R at count=gt) | ~0.78 |
> | Stage selection | F1 / recall (answerable stages, one_call) | ~0.48 / ~0.54 |
> | L3 capability | F1 / recall / precision (answerable, one_call) | ~0.62 / ~0.87 / ~0.48 |
> | Theme Description | faithfulness / hallucination / coverage | 0.94 / 0.06 / 0.77 |
> | Business Needs | faithfulness / hallucination / coverage | 0.90 / 0.10 / 0.81 |
> | Business Needs (structural) | stage usage / stage alignment | 1.00 / 0.86 |

> **Key findings.** (1) The new-ticket **raw prompt** is the main lever for VS selection; **summary
> retrieval** beats raw-embedded retrieval — so summarisation stays for retrieval. (2) For the
> selection components, **removing the per-element count cap** recovered substantial recall (the
> count is the lever); the residual gap is largely **ground-truth label noise** (selections the
> architect made from convention, not derivable from the ticket) plus **catalogue coverage gaps**
> (ground truth tagged at theme level mapping to stages/capabilities outside the selection).
> (3) **Cross-element mislinking** is prevented by strict-isolation prompts and corrected by the
> salvage layer (≈0). (4) For the generative components, a **grounding prompt rule** (every claim
> must trace to an idea-card phrase) was the lever, trading a little completeness for far less
> invention — the right trade for an architect-facing artifact.

> **Cost.** Each component reports per-call generation latency and token usage (prompt / completion)
> for capacity planning; the batched architecture keeps the per-ticket call count low (~23 LLM
> calls for a 10-VS / ~3-stage ticket).

---

# Summary checklist (for the editor)
- [ ] §6.2: generation input changed from summaryFields+signals to **raw idea-card text** (all 4 generators)
- [ ] §6.2: stage selection — **no count cap**, strict VS isolation + salvage, never-empty fallback, boundary handling
- [ ] §6.2: capabilities — **no count cap** (remove the "precision bias / typically 1–3" wording), strict stage isolation + salvage, L2 derived
- [ ] §6.2: description body/framing + business needs — **grounding rule** (explicit-in-card only; no inferred availability/dependencies/rules/training)
- [ ] §6.1: orchestration input note = raw text; add the salvage sentence
- [ ] §4/§5: historic index doc is **retrieval-only** (searchText + vector + key); VS labels/content from Cosmos by key; candidates from catalogue
- [ ] §3: condense budget ~24k tokens, greedy idea-card-first packing, cap 8
- [ ] §7 (new): Evaluation section — method, locked results table, key findings, cost
- [ ] Figures 2 and 3 updated (raw input, no count cap, salvage, retrieval-only index)
