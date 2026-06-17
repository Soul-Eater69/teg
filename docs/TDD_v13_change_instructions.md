# TDD v13 → v14 change instructions

**For:** the coworker maintaining the TDD docx.
**Input file:** `tdd_updated_v13.docx`  ·  **save as:** `tdd_updated_v14.docx`

This pass fixes the **storage schemas** (§2 and §4) and **Figure 1**. The field lists below are the
**authoritative target** — match them exactly. Each item names the section + the table it lives in (by
field signature) so there's no ambiguity.

---

## Part A — Figure 1 (ingestion diagram): stop at Cosmos + index

The ingestion flow must **end at the Cosmos write + the `idp_teg_data` index**. **Remove the block(s)
after that** (the data-science / retrieval / Value-Stream-recommendation stage) — that belongs to
Figure 2, not the ingestion diagram. Ingestion's last nodes are: *consolidate → condense → write Cosmos
documents + upsert index*. Nothing downstream of the index appears in Figure 1.

(The Figure 1 image is also still a stale render from the earlier pass — re-render it from
`docs/TDD_diagrams_only_instructions.md` with "up to 8 attachments", retrieval-only index, and now this
"stop at Cosmos + index" boundary.)

---

## Part A2 — Remove the "Summary to find, raw to decide" note box from the diagram

The diagram with the legend (*Input / Deterministic / LLM call / Stored output / Note / principle*)
contains a purple **Note / principle** box reading:

> *"Summary to find, raw to decide — summaryFields and the searchText/content_vector pair support
> retrieval and routing only. All downstream theme-generation calls (Figure 3) read rawText directly
> from the Cosmos document — never summaryFields, never generationSignals (no such field is produced or
> stored)."*

**Remove this note box** and re-render the diagram without it. Two reasons:
- It's now **inaccurate** — it claims "no such field is produced or stored", but `businessSummary` (the
  LLM-generated summary) **is** produced and stored in `properties` (Part D). The blanket "never
  summaryFields" wording reads as if nothing is stored, which is wrong.
- The "generation reads rawText" point is already stated correctly in the §6.2 prose, so the box is
  redundant clutter on the figure.

> If you'd rather keep a one-line principle instead of deleting outright, replace the whole box with:
> *"Theme generation reads `rawText` directly; the stored summary fields and the index
> (`searchText`/`content_vector`) are for retrieval only."* — but the default is **remove it**.

---

## Part B — §2 Source of Truth table (the "Entity / Source of Truth / Destination" table)

Change the **Value Stream** (and Value Stage / L2 / L3 catalogue) rows: their **Source of Truth is the
Azure SQL DB** (the org's existing gold catalogue), **not Cosmos**. We consume it as-is; we do **not**
define or store a Value Stream catalogue schema. Update the Destination column accordingly (no Cosmos
catalogue write for Value Streams).

---

## Part C — §4.1 Cosmos IDMT document, top-level fields (table: `id, key, source, sourceId, …, parentRef, properties`)

**Add one field:**

| field | description |
|---|---|
| `domain` | constant `"WORKITEM"` — present on every IDMT and Theme document |

Everything else in this table is correct (`id`=uuid, `key`=IDMT-####, `sourceId`=7-digit stable id,
`createdAt/createdBy/lastModifiedAt/lastModifiedBy`=ingestion lifecycle, `parentRef`=null for ER).

---

## Part D — §4.2 Cosmos IDMT `properties` (table starting `properties.description, properties.summary, …`)

**Remove ONE row only:**
- ✅ `properties.businessSummary` — **KEEP it** (LLM-generated business summary; it **is** stored).
- ❌ `properties.themes` — **delete it**. Themes are **not** attached to the IDMT document. A Theme is
  found by querying Theme documents whose `parentRef` = this IDMT's 7-digit id (Part F), not by an
  embedded array.

Resulting `properties` for the IDMT doc: `description`, `summary` (the ticket **title**), `creationDate`
/ `insightsTime`, **`businessSummary`**, `rawText`, `keyTerms`, `businessProblem`, `businessCapability`,
`stakeholders`, `systemsAndProducts`. (`businessSummary` **stays**; only `themes` is removed.)

---

## Part E — §4.3 "Cosmos properties.themes array object" (table: `sourceId, key, valueStreamId, valueStreamName`)

**Delete this whole sub-section (§4.3 heading + its table).** The themes array no longer exists on the
IDMT document (see Part D).

---

## Part F — §4.4 Cosmos Theme document, top-level fields (table currently: `id, source, groupId, entityType, parentId, parentEntityType, createdDate, …`)

This table is wrong. **Replace the top-level field list** so the Theme doc mirrors the IDMT doc shape:

| field | description |
|---|---|
| `id` | document uuid |
| `key` | the **Theme id** (e.g. `GROUP-23618`) |
| `source` | `"Jira"` |
| `sourceId` | the Theme's **7-digit stable id** |
| `entityType` | `"Theme"` |
| `domain` | constant `"WORKITEM"` |
| `createdAt` / `createdBy` | **ingestion** lifecycle (when we wrote it to Cosmos — NOT the Theme's Jira dates) |
| `lastModifiedAt` / `lastModifiedBy` | **ingestion** lifecycle |
| `parentRef` | the **7-digit id of the parent** IDMT/ER |
| `properties` | (see Part G) |

Remove the old fields: `groupId`, `parentId`, `parentEntityType`, and the `createdDate/modifiedDate/
modifiedBy` naming. The Theme's *own* created/modified dates move into `properties` (Part G).

---

## Part G — §4.5 Cosmos Theme `properties` (table currently: `properties.description, properties.title`)

**Replace** the properties list with exactly these five:

| field | description |
|---|---|
| `summary` | the **title** of the Theme |
| `description` | the Theme description |
| `valueStream` | a string in the format **`"<ValueStreamName> {vs_id}"`** (e.g. `"Resolve Appeal {VSR00074590}"`) |
| `creationDate` | the **Theme's** created date |
| `insightsTime` | the **Theme's** last-modified date |

(Drop the old `properties.title` row — it's now `summary`.)

---

## Part H — §4.6, §4.7, §4.8, §4.9 Cosmos Value Stream catalogue: DELETE all four

**Remove the entire Value Stream catalogue from Cosmos** — headings and tables for:
- §4.6 Cosmos Value Stream catalogue document — top-level fields
- §4.7 catalogue properties object
- §4.8 catalogue `properties.valueStages` array object
- §4.9 catalogue capability object

We do **not** store Value Streams / stages / capabilities in Cosmos. That data is the org's **Azure SQL
DB** gold catalogue, consumed as-is — no schema definition is ours to own. Add one sentence where §4.6
used to be: *"Value Stream, Stage, and L2/L3 capability catalogue data is sourced from the Azure SQL DB
(org gold data) and is not redefined or stored here."*

---

## Part I — §4.10 / §4.11 idp_teg_data historical IDMT index document

The index is **retrieval-only**. **Replace** the field list (currently `id, source, sourceId,
entityType, searchText, content_vector, properties`) with exactly:

| field | description |
|---|---|
| `key` | IDMT business key (e.g. `IDMT-19761`) — the index document key |
| `sourceId` | 7-digit stable id |
| `entityType` | e.g. `EngagementRequest` |
| `status` | record status |
| `searchText` | the text that is embedded / retrieved on |
| `content_vector` | embedding vector |

- Remove `id`, `source`, and the `properties` wrapper.
- **Delete §4.11 "Historical index properties object"** (the `properties.summary` table) — there is no
  `properties` object on the index doc; all Value Stream / ticket detail is enriched at query time from
  Cosmos / Azure SQL, not stored in the index.

> Note: if the Azure AI Search index's key field must literally be named `id`, keep that key field but
> populate it with the IDMT key; the six fields above are the complete stored set either way.

---

## Part J — §4.12 / §4.13 idp_teg_data Value Stream index document  (CONFIRM)

You only specified the historical-IDMT index doc. The Value Stream **index** document (§4.12/§4.13)
still exists for semantic VS retrieval, but for consistency it should be the same retrieval-only shape
(`key`, `sourceId`, `entityType`, `status`, `searchText`, `content_vector`), with the VS detail
(`valueStreamName`, `description`, `category`, …) **enriched from Azure SQL at query time**, not stored
in `properties`. **Confirm** you want this aligned the same way; if yes, apply the Part I treatment to
§4.12/§4.13 too and delete the §4.13 properties table.

---

## Part K — code reconciliation note (FYI, not a docx edit)

For the record, the current ingestion writer (`src/teg/ingestion/documents/idmt_documents.py`):
- **`properties.businessSummary`** — already matches (keep it; no code change).
- **`properties.themes[]`** — still emitted; needs to be **dropped** to match the new schema.
- **`domain: "WORKITEM"`** and the new Theme/index shapes — not yet emitted; need to be added.

The **docx schema above is authoritative**; the ingestion code needs a follow-up change for the `themes`
removal, `domain`, and Theme/index shapes (separate task — not part of this docx pass).

---

## Verification checklist before saving v14

- [ ] Figure 1 ends at Cosmos + index (no downstream block); re-rendered, 8 attachments.
- [ ] "Summary to find, raw to decide" note box removed from the diagram (Part A2).
- [ ] §2 table: Value Stream SoT = Azure SQL DB.
- [ ] IDMT doc has top-level `domain: "WORKITEM"`; `properties` **keeps** `businessSummary`, **removes** `themes`.
- [ ] §4.3 themes-array section deleted.
- [ ] Theme top-level = id / key / source / sourceId / entityType / domain / createdAt / createdBy / lastModifiedAt / lastModifiedBy / parentRef; Theme `properties` = summary / description / valueStream / creationDate / insightsTime.
- [ ] §4.6–4.9 (Cosmos VS catalogue) deleted; replaced with the one-line Azure SQL note.
- [ ] Historical index doc = key / sourceId / entityType / status / searchText / content_vector; §4.11 deleted.
- [ ] §4.12/§4.13 VS index doc — confirmed + aligned (Part J).
- [ ] Search whole doc for `properties.themes`, `groupId`, `parentEntityType` → 0 hits (but
      `businessSummary` should still be present in §4.2).
- [ ] Save as `tdd_updated_v14.docx`.
