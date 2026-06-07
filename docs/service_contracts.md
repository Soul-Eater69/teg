# TEG Service I/O Contracts (for the Backend team)

Status: **DRAFT for review** · Target handoff: Monday

This is the data contract for the three services the backend calls. It is **not** an
API spec - routes, auth, transport, and HITL are the backend's. We own only the
request/response shapes and behavior below. The shapes are also defined in code
(`src/teg/contracts/`); generate JSON Schema with
`Model.model_json_schema(by_alias=True)`.

## Ownership

| Concern | Owner |
| --- | --- |
| API routes, auth, transport, HITL | Backend |
| Storing condensed data between steps | Backend (we return it; they replay it) |
| Condense / VS prediction / Theme generation | TEG (us) |
| Historical ingestion -> Cosmos + `idp_idmt_data` | TEG, offline batch (see Open #1) |
| Governed VS / stage / L2 / L3 catalogues | TEG (read from Cosmos; backend never sends them) |

## Flow

```
new idea card
  -> [A: Condense]          -> condensed data ──(backend stores it)
  -> [B: VS prediction]     -> recommendations + 6 historical tickets
        -> backend HITL: SME approves the VS set
  -> [C: Theme generation]  -> one theme package per approved VS
```

JSON is `camelCase`. Field shapes follow the TDD (sections noted per contract).

---

## Contract A - Condense  (`contracts/condense_io.py`)

**Request** `CondenseRequest`
- `ticketId` (string, required) - the only input. We fetch from Jira, locate the idea
  card (`idea_card.ppt`/`idea_card.pptx`), and fall back to the top-4 attachments
  (PPT->PDF->DOC) when it is absent. Attachment text extraction is text-layer only
  (pypdfium2 / python-pptx / python-docx); no OCR, legacy .ppt/.doc skipped.

**Response** `CondenseResponse.condensed` = `CondensedTicket` (backend stores + replays):
- `ticketId`, `ticketTitle`, `primarySource` (`idea_card`|`attachments_fallback`), `attachmentsUsed[]`
- `summaryFields`: `generatedSummary`, `businessProblem`, `businessCapability`, `keyTerms[]`, `stakeholders[]`, `systemsAndProducts[]`
- `generationSignals`: 18 arrays of `{text, source, sourceSection}`; `[]` when absent, never invented
- `description`, `rawText`

---

## Contract B - Value Stream prediction  (`contracts/value_stream_io.py`)

**Request** `ValueStreamRequest`
- `ticketId`, `summaryFields` (replayed from A)
- `requestedCount` (default 10, upper bound), `customInstruction` (optional)
- `selectedHistoricalTicketIds[]` (optional - the SME-selected analogs; see Open #3)

**Response** `ValueStreamResponse`
- `recommendations[]`: `valueStreamId`, `valueStreamName`, `confidence` (0.30-1.00), `supportType` (`direct`|`implied`), `reason` (<=80 chars), `bucket`, `sourceTickets[]`
- `historicalTickets[]`: top-6 analogs `{ticketId, title, score, snippet}` for the HITL selection step

---

## Contract C - Theme generation  (`contracts/theme_io.py`)

**Request** `ThemeGenerationRequest`
- `ticketId`, `ticketTitle`
- `condensed`: `{summaryFields, generationSignals}` (replayed from A)
- `approvedValueStreams[]`: `{valueStreamId, valueStreamName}`

**Response** `ThemeGenerationResponse.themePackages[]` (one per approved VS):
- `themeTitle` (deterministic: `"<ticketTitle> - <valueStreamName>"`)
- `themeDescription`: `themeOverview`, `initiativeOverview`, `keyFeatures[]`, + optional `productAvailability`, `digitalExperience`, `integrationOperationalCapabilities`
- `selectedStages[]`: `{stageId, stageName, rank, reason, evidence, validationStatus}`
- `businessNeeds[]`: `{stageId, stageName, businessProductFeatures[{featureName, needs[], notes, dependencies[], businessRules[]}], operationalTraining?, operationalReporting?, validationStatus}`
- `l2Capabilities[]` / `l3Capabilities[]`: grouped by stage, each `{name, description, reason}`
- `validationStatus`: `recommendation` until SME approves writeback

---

## Open items - need a decision before final handoff

1. **Ingestion trigger** - backend-triggered or our offline batch? Assumed: our offline batch (no live contract).
2. ~~Who fetches Jira~~ - RESOLVED: backend sends only `ticketId`; we fetch from Jira and resolve the idea card / attachments.
3. **Historical-ticket HITL** - does the SME pick the 6 analogs inside B (then B splits into `retrieveCandidates` + `predict`), or auto-use? Assumed: single call, auto-use, `selectedHistoricalTicketIds` optional.
4. **Sync vs async transport** - VS ~35s, theme generation longer. Blocking HTTP, or job + poll/stream? Recommend async job for C (and optionally B). Backend's call.
5. **Theme call granularity** - one C call returning all packages, or one per approved VS (better progress/partial-failure)? Assumed: one call, array response.
6. **Error / partial-failure envelope** - desired error shape + per-VS `validationStatus` for partial theme failures.
