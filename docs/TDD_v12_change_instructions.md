# TDD v12 → v13 change instructions

**For:** the coworker maintaining the TDD docx.
**Input file:** `tdd_updated_v12.docx`  · **save as:** `tdd_updated_v13.docx`

## Why a second pass

The v12 prose pass was good — most text changes from the v11 instructions landed correctly.
**§6 Theme Generation is fully correct and must NOT be touched** (it already says generation reads
raw idea-card text and every sub-call says "no generationSignals" — see the "leave alone" note in
Part D).

But three things were **not** updated and still show old data:

1. **All three figures are stale images** — they still show `generationSignals` and "4 attachments".
   The prose around them was fixed; the PNGs were never re-rendered.
2. **§4.3 Cosmos IDMT document example** still contains a `generationSignals` block (and a few other
   wrong fields). The ingested Cosmos document does **not** store generation signals.
3. **§5.1 Condense** still presents `generationSignals` as a live output and calls `summaryFields`
   "LLM context", which is no longer true.

These are the only stale spots. Everything below is precise and bounded.

---

## Part A — Regenerate all 3 figures (the main miss)

The three inline images (Figure 1, 2, 3) are old renders. The exact specs are already in
`docs/TDD_diagrams_only_instructions.md` — re-render from those. Each figure must now reflect:

**Figure 1 — End-to-end ingestion flow** (caption para 31)
- "Up to **8** supported attachments" (not 4).
- The condense step writes **summaryFields + rawText** into Cosmos — **remove any `generationSignals`
  box** from the Cosmos write.
- `idp_teg_data` is **retrieval-only**: it stores only `searchText` + `content_vector` (ids in, ranked
  ids out). No label/signal payload in the index.

**Figure 2 — Data science / retrieval flow** (caption para 233)
- Retrieval-only index returns **ranked ids**; Value Stream + historical-ticket details are **enriched
  from the governed catalogue / Cosmos**, not from the index.
- **Remove** the historic "direct/implied classification" node (it was removed — see §5.4 prose,
  para 300). The generic-stream penalty stays.

**Figure 3 — Theme generation flow** (caption para 399)
- Generation reads **raw idea-card text** — no `generationSignals`, no `summaryFields`.
- Call topology: **3 ticket-level calls + 2 per Value Stream (3 + 2N)**, with the salvage step after
  each batched selection. (This matches the already-correct §6.1 prose — just make the picture agree.)

> Quickest path: open `TDD_diagrams_only_instructions.md`, render each diagram, and replace the three
> inline images in place. Keep the existing captions.

---

## Part B — §4.3 Cosmos IDMT document example (paras 47–95): replace the JSON

The example is stale: it has a `generationSignals` block, a non-existent `title` field, reversed
`id`/`sourceId`, and old top-level lifecycle field names. The **actual** ingested document
(`src/teg/ingestion/documents/idmt_documents.py`) stores exactly these fields. Replace the whole
example block with:

```json
{
  "id": "<deterministic-doc-uuid>",
  "key": "IDMT-19761",
  "sourceId": "3364549",
  "source": "Jira",
  "entityType": "EngagementRequest",
  "createdAt": "2026-06-01T00:00:00Z",
  "createdBy": "ingestion",
  "lastModifiedAt": "2026-06-01T00:00:00Z",
  "lastModifiedBy": "ingestion",
  "parentRef": null,
  "properties": {
    "description": "Original Jira description text ...",
    "summary": "Enabling Real-Time Quote Automation for Enterprise Accounts",
    "creationDate": "2024-05-31T08:12:12-05:00",
    "insightsTime": "2025-12-31T09:47:10-06:00",
    "businessSummary": "Sales Operations needs a real-time CPQ integration ...",
    "keyTerms": ["CPQ", "quoting", "enterprise", "Salesforce"],
    "businessProblem": "Manual quoting delays enterprise deal closures by 3-5 days.",
    "businessCapability": "Automated real-time quote generation for enterprise accounts.",
    "stakeholders": ["Sales Ops", "IT", "Finance"],
    "systemsAndProducts": ["Salesforce CPQ", "Oracle ERP", "Deal Desk Portal"],
    "rawText": "Consolidated raw text from description + up to 8 extracted attachments, greedily packed into a ~24k-token budget ...",
    "themes": [
      {
        "key": "GROUP-23618",
        "sourceId": "3966046",
        "valueStreamId": "VSR00074590",
        "valueStreamName": "Resolve Appeal"
      }
    ]
  }
}
```

Key changes to call out (so they're not "corrected" back):
- **Deleted the entire `generationSignals` block** — it is never stored in the Cosmos IDMT document.
- `key` = `IDMT-####` (business key); `sourceId` = stable Jira id (e.g. `3364549`); `id` = deterministic
  doc uuid. (v12 had `id`/`sourceId` swapped.)
- Top-level lifecycle fields are `createdAt / createdBy / lastModifiedAt / lastModifiedBy / parentRef`
  (not `createdDate/modifiedDate/modifiedBy`).
- `properties.summary` = the ticket **title**; the LLM summary is `properties.businessSummary`. There
  is **no** separate `title` field.
- `creationDate` / `insightsTime` (source ticket dates) live **inside** `properties`.
- Each `themes[]` entry is `{key, sourceId, valueStreamId, valueStreamName}` (v12 used `groupId` —
  it's stored as `key`).

If §4.1 / §4.2 (the field tables) still list `generationSignals` as a `properties` field, remove that
row too.

---

## Part C — §5.1 Condense Step (paras 234–287): the generationSignals decision

Generation no longer consumes generation signals (raw text only), the Cosmos doc doesn't store them,
and retrieval uses `searchText`. So `generationSignals` has **no downstream consumer**. Two edits:

1. **Para 235 (intro sentence).** Change
   *"summaryFields for retrieval, routing, and LLM context, and generationSignals …"* →
   **"summaryFields for retrieval and routing"**. `summaryFields` are not used as LLM/generation
   context anymore — generation reads raw text.

2. **Contract A response (paras 248–287).** **Remove the `generationSignals` block** (paras 262–281)
   and the para 242 paragraph that describes the signal arrays. The response keeps:
   `ticketId, ticketTitle, primarySource, attachmentsUsed, summaryFields{…}, description, rawText`
   plus `model` / `promptVersion`.

   > **Decision flag (confirm with the team):** the condenser code still *computes* signals internally
   > (the two-pass condense). If the design intent is to keep producing them for a future consumer,
   > instead of deleting, add one line under Output fields: *"generationSignals are computed but not
   > currently consumed by retrieval, storage, or generation (reserved)."* Default recommendation is
   > **remove** — no consumer reads them today, and leaving them in the contract is what made the doc
   > look stale. Pick one and apply it consistently.

3. **§5.2 (para 290).** "Both paths produce the same normalized context object: generated summary,
   description, raw text, key terms, business problem, business capability, stakeholders, systems/
   products." — this is already correct (no signals listed). Leave as-is.

---

## Part D — Leave-alone list (do NOT revert these — they're already correct)

These were fixed in v12 and are right; don't let a find-replace touch them:

- **§6.1 / §6.2 (paras 396–451)** — theme generation already states it reads **raw idea-card text**,
  "no generationSignals" / "no summaryFields/generationSignals" on every sub-call (stage selection,
  description body+framing, business needs, capabilities), "no count cap", STRICT ISOLATION + salvage,
  and the **3 + 2N** call topology. All correct. **Do not add signals back here.**
- **§2 / §4 intro** — "idp_teg_data is retrieval-only: `searchText` and `content_vector`". Correct.
- **§3 ingestion** — "Up to 8 supported attachments", "~24k-token budget using greedy packing".
  Correct in prose (only the Figure 1 image is wrong — Part A).
- **§5.4 (para 300)** — direct/implied classification removed; generic-stream penalty retained.

---

## Verification checklist before saving v13

- [ ] Search the whole doc for **`generationSignals`** → it should appear **0 times** (or only in the
      single "reserved/not consumed" sentence if the team chose to keep it in §5.1).
- [ ] Search for **"4 attachment"** / **"four attachment"** → **0 hits** (should be 8 everywhere,
      including inside the figures).
- [ ] All **3 figures** re-rendered; open each and confirm no `generationSignals` box and "8 attachments".
- [ ] §4.3 example matches the JSON in Part B (no `title`, has `businessSummary`, correct
      `key`/`sourceId`).
- [ ] §6 untouched.
- [ ] Save as `tdd_updated_v13.docx`.
