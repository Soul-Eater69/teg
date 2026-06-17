TECHNICAL DESIGN DOCUMENT
Theme & Epic Generation
Ingestion and Data Science Solution
Contents
1.  Executive Summary
   1.1  How it works (overview)
   1.2  End-to-end flow
2.  Source of Truth and Data Ownership
3.  Ingestion Design Flow
4.  Target Storage and Unified Index Schema
5.  Data Science Solution
   5.1  Condense Step
   5.2  Ticket Context Extraction
   5.3  Historical Ticket Retrieval
   5.4  Value Stream Candidates
   5.5  LLM Selection Prompt and Output
   5.6  Quality Metrics for Value Stream Selection
6.  Theme Generation Solution
   6.1  Orchestration Sequence
   6.2  Context Passed to Each Generation Call
   6.3  Final Theme Package Returned for Review


1. Executive Summary
SMEs and Business Architects analyze IDMT Engagement Requests, review idea cards and attachments, select approved Value Streams and Stages, and create Jira Themes, Epics and capability hierarchies. The solution accelerates that workflow by producing a structured, evidence-backed recommendation package for SME review.
The design has two modules: an ingestion module that converts historical IDMT tickets into a trusted corpus with lineage and ground-truth labels, and a data science module that uses governed catalogues plus historical evidence to recommend Value Streams, Stages, Theme content, Business Needs, and L2/L3 capabilities. The SME remains the final approver; Jira remains the system of record for approved artifacts.
1.1 How it works (overview)

Figure 0. The flow at a glance — where the system uses an LLM and where it doesn’t.
The tool mirrors what a Business Architect does by hand. It uses an LLM only for the parts that are genuine judgment or writing — understanding a messy idea card, deciding which business areas (Value Streams) a change touches, and drafting each Theme’s description, needs and capabilities. Everything mechanical — searching for similar past work, and stitching the final package together — runs automatically with no LLM. A person approves the Value Streams before anything is written.
So a single request makes a small, fixed set of LLM calls: one to understand the ticket, one to choose the Value Streams, then a few to write each approved Theme — not a brute-force sweep. Each call maps to one decision a Business Architect would otherwise make manually.
1.2 End-to-end flow
The pipeline has two phases. Phase A (ingestion) runs offline over historical tickets to build the corpus (Cosmos system-of-record + the retrieval index). Phase B (runtime) runs per new ticket to produce Theme packages, reusing the same Condense step and reading what Phase A stored.

Figure 0.1. End-to-end flow (detail): ingestion (Phase A) builds the corpus; runtime (Phase B) reuses Condense and produces Theme packages.
Phase A — Ingestion
| Stage | LLM? | Input → output | Key rule |
|---|---|---|---|
| Jira fetch | no | ticket id → raw packet + linked Theme/Epic ids | ER after 2023-01-01 with a linked Theme |
| Attachment extraction + idea-card detection | no | attachments → extracted text | PPT→PDF→DOC, up to 8 |
| Raw text assembly | no | extracted texts → rawText | ~24k-token greedy pack, priority order |
| Condense | LLM ×1 | rawText → summaryFields + rawText | summary to find, raw to decide |
| Ground-truth extraction | no | linked Themes/Epics → VS + stage/L3 GT | read the recorded answer; drop uncatalogued |
| Embed → Cosmos + index | embedding | retrieval text → SoR docs + index vectors | index = searchText + content_vector only |

Phase B — Runtime
| Stage | LLM? | Input → output | Key rule |
|---|---|---|---|
| Condense (new ticket) | LLM ×1 | rawText → summaryFields + rawText | reused from ingestion |
| Retrieve top-6 historical | embedding | summary → 6 similar tickets | retrieval query = summary |
| Load 50 Value Streams | no | — → 50 VS catalogue | Azure SQL gold data; not retrieved |
| Value Stream Selection | LLM ×1 | raw text + 50 VS + 6 historical summaries → recommendations | raw is the lever; no lanes/ranking |
| HITL approval | human | recommendations → approved VS set | nothing generates before this |
| Stage Selection | LLM ×1 | raw + per-VS candidate stages → selectedStages/VS | all VS batched; no count cap; salvage |
| Description BODY + FRAMING | LLM ×2 | raw (+ per-VS detail for framing) → body + per-VS framing | grounding rule (every claim traces to a phrase) |
| Business Needs | LLM ×N | raw + VS + selected stages → Business Needs text | 1 call per VS; one block per stage |
| Capabilities (L3) | LLM ×N | raw + VS + per-stage candidate L3 → L3 per stage | 1 call per VS; stage isolation + salvage |
| Assembly (L2, title, package) | no | generated parts → Theme package per VS | L2 = unique parent of L3; title = template |

Per new ticket: 5 + 2N LLM calls (+1 embedding); retrieval, catalogue load, L2, salvage, title and assembly use no generation call. Wall-clock ≈ 27s end-to-end, excluding the HITL gate.
Phase A storage shapes are in §4; runtime selection in §5; theme generation in §6; measured quality per stage in §7 / the EDA documents.
2. Source of Truth and Data Ownership
The table below captures authoritative inputs, target stores and value added by each curated asset. idp_teg_data is the sole AI Search index and is retrieval-only: it stores searchText and content_vector for each entity, separated by metadata and document style. Cosmos (for Engagement Requests) and the Azure SQL DB (for Value Streams) remain the sources of truth for full content and ground-truth labels.
| Entity | Source of Truth | Destination | Extraction / Processing |
|---|---|---|---|
| Engagement Request (ER) | Jira API + iTech DB audit | Cosmos historic IDMT document + idp_teg_data | iTech DB identifies eligible ERs and Theme links. Jira API fetches description, attachments and Theme data. Extraction, LLM summary, and VS fuzzy match with LLM confirmation enrich the record. The themes[] ground truth stores only valueStreamId and valueStreamName for each resolved Value Stream. Only searchText and content_vector are written to idp_teg_data for retrieval; the full ticket record and themes[] ground truth are read from Cosmos by sourceId when needed. |
| Value Stream | Azure SQL DB | Azure SQL DB (consumed as-is; not written to Cosmos or idp_teg_data by the ingestion module) | dedupe, JSON organization, metadata tagging and ingestion into the unified search index. Only searchText and content_vector are written to the idp_teg_data valueStream document for retrieval; valueStreamName, valueStreamDescription, category and valueProposition are read from the governed Cosmos catalogue file by valueStreamId. |
| Value Stage, L2, L3 | Azure SQL DB | Azure SQL DB (consumed as-is) | organize, version and ingest. |
| Theme details | Jira API | Cosmos historic IDMT document; | Theme description text extraction; |

3. Ingestion Design Flow
End-to-end ingestion sequence

Figure 1. End-to-end ingestion flow using iTech DB for eligibility audit and idp_teg_data as the unified AI Search index.
The ingestion module starts by identifying usable historical tickets instead of ingesting every IDMT ticket. The iTech DB audit finds Engagement Requests after 2023-01-01, checks Theme links, confirms issue type, and limits ingestion to records with valid or partially valid approved Value Stream ground truth. The selected records are then fetched from Jira, enriched, persisted in Cosmos, and indexed into idp_teg_data.
•   Attachment extraction prioritizes the likely idea card: PPT/PPTX first, then PDF, then DOC/DOCX. Up to 8 supported attachments are extracted.
•   PPT is prioritized because SMEs confirmed it is the most common idea-card format.
•   The consolidated raw idea-card text (description + extracted attachments) is assembled into a single ~24k-token budget using greedy packing: content is added in source-priority order (idea card first, then description, then the remaining supported attachments, up to the 8-attachment cap) until the budget is reached, so the highest-priority material is never displaced or truncated to make room for lower-priority material. This raw text - not summaryFields or generationSignals - is what theme-generation calls read (see section 6.2).
•   Only approved Value Stream and Stage names pass validators; invalid or unsupported labels are excluded from ground-truth training data.
4. Target Storage and Unified Index Schema
Cosmos stores durable source lineage, historical ground truth, catalogue metadata and future SME feedback. idp_teg_data is the unified AI Search index. It contains multiple document styles separated by entityType and metadata: historical IDMT documents and Value Stream catalogue documents.
4.1 Cosmos historic IDMT document - top-level fields
| Field | Description |
|---|---|
| id | Deterministic document UUID derived from source + sourceId; the document’s permanent identifier in Cosmos |
| key | Jira issue key / business key, e.g. IDMT-#### (mutable) |
| source | Origin system, e.g., Jira |
| sourceId | Stable Jira internal issue id, e.g. 3364549; stable across IDMT-key changes |
| entityType | Entity category, e.g., EngagementRequest |
| domain | constant "WORKITEM" — present on every IDMT and Theme document |
| createdAt | Cosmos document creation timestamp (ISO 8601, UTC) |
| createdBy | Actor that created the document, e.g. ingestion |
| lastModifiedAt | Cosmos document last-modified timestamp (ISO 8601, UTC) |
| lastModifiedBy | Actor that last modified the document, e.g. ingestion |
| parentRef | Reference to a parent document, or null for top-level entities |
| properties | Nested object containing extracted business context and theme ground truth |

4.2 Cosmos properties object
| Field | Description |
|---|---|
| properties.description | Original Jira description or cleaned description |
| properties.summary | Ticket title (the source ticket’s summary field) |
| properties.creationDate / properties.insightsTime | Source ticket creation date and last-insights-refresh timestamp (source dates, distinct from the top-level createdAt/lastModifiedAt) |
| properties.businessSummary | LLM-generated business summary |
| properties.rawText | Consolidated raw context from description and up to 8 extracted attachments, greedily packed into a ~24k-token budget in source-priority order. This is the raw idea-card text read directly by theme-generation calls (section 6.2) |
| properties.keyTerms | Domain terms and acronyms |
| properties.businessProblem | Business problem / pain point |
| properties.businessCapability | Desired capability or outcome |
| properties.stakeholders | Stakeholder groups |
| properties.systemsAndProducts | Referenced systems, platforms and products |

4.4 Cosmos Theme document - top-level fields
| Field | Description |
|---|---|
| id | document uuid |
| key | the Theme id (e.g. GROUP-23618) |
| source | "Jira" |
| sourceId | the Theme's 7-digit stable id |
| entityType | "Theme" |
| domain | constant "WORKITEM" |
| createdAt / createdBy | ingestion lifecycle (when the document was written to Cosmos — NOT the Theme's Jira dates) |
| lastModifiedAt / lastModifiedBy | ingestion lifecycle |
| parentRef | the 7-digit id of the parent IDMT/ER |
| properties | (see §4.5 below) |

4.5 Cosmos Theme properties object
| Field | Description |
|---|---|
| summary | the title of the Theme |
| description | the Theme description |
| valueStream | a string in the format "<ValueStreamName> {vs_id}" (e.g. "Resolve Appeal {VSR00074590}") |
| creationDate | the Theme's created date |
| insightsTime | the Theme's last-modified date |

Value Stream, Stage, and L2/L3 capability catalogue data is sourced from the Azure SQL DB (org gold data) and is not redefined or stored here.
4.10 idp_teg_data - historical IDMT index document
| Field | Description |
|---|---|
| key | IDMT business key (e.g. IDMT-19761) — the index document key |
| sourceId | 7-digit stable id |
| entityType | e.g. EngagementRequest |
| status | record status |
| searchText | the text that is embedded / retrieved on |
| content_vector | embedding vector |

4.12 idp_teg_data - Value Stream index document
| Field | Description |
|---|---|
| key | Value Stream id (e.g. VSR00074590) — the index document key |
| sourceId | Value Stream id (stable identifier) |
| entityType | ValueStream |
| status | record status |
| searchText | the text that is embedded / retrieved on |
| content_vector | embedding vector |

The historical document content vector is generated from curated structured text rather than raw Jira markup. This keeps retrieval focused on business intent and avoids boilerplate, comments and attachment noise.
5. Data Science Solution
Once Cosmos and idp_teg_data are populated, the data science flow starts from a user-provided IDMT ticket id. The service first extracts the current ticket context from Jira, then retrieves the top 6 most similar historical Engagement Request documents from idp_teg_data and combines them with the full 50-VS catalogue supplied from the Azure SQL DB. The result is a ranked, evidence-backed Value Stream recommendation set for SME review.

Figure 2. Data science flow from IDMT ticket id to ranked Value Stream recommendations.
5.1 Condense Step
The condense step is the first LLM call in the data science flow. It extracts structured context from the IDMT ticket source material in a single pass and returns summaryFields for retrieval and routing. A single extraction pass avoids re-processing the same idea card or attachment text downstream. The condense step also produces rawText, the consolidated raw idea-card text (~24k tokens, greedily packed - see section 3). Summaries are used to find; raw text is used to decide: Theme Description, Business Needs, Stage Selection and Capability generation calls (section 6.2) read rawText directly, not summaryFields.
Source priority
•   If an attachment named or tagged idea_card.ppt / idea_card.pptx exists, use it as the primary business context source.
•   If the idea card is missing, fall back to the Jira ticket description plus the supported attachments (up to the 8-attachment cap) in priority order: PowerPoint, PDF, Word document.
•   The description and selected attachments are concatenated into the raw idea-card text and packed greedily into a ~24k-token budget in source-priority order, so the idea card (or description) is never truncated to fit lower-priority attachments. This raw text - not summaryFields or generationSignals - is what theme-generation calls read (section 6.2).
Output fields
| Group | Fields | Used by |
|---|---|---|
| summaryFields | generatedSummary, businessProblem, businessCapability, keyTerms, stakeholders, systemsAndProducts | VS selection, stage selection, Theme Description, Business Needs, L2, L3 |

Contract A — Request  (POST /api/condense)
Request: ticketId.
Contract A — Response
Response: condensed { ticketId, ticketTitle, primarySource, attachmentsUsed[], summaryFields {generatedSummary, businessProblem, businessCapability, keyTerms, stakeholders, systemsAndProducts}, description, rawText }, plus model, promptVersion.
5.2 Ticket context extraction
The user provides an IDMT ticket id. The Jira API is used to inspect the ticket attachments and locate an attachment explicitly tagged or named idea_card.ppt / idea_card.pptx. If the idea card is present, it is treated as the primary source of business context. If the idea card is not found, the fallback path summarizes the IDMT ticket description and extracts the up to 8 supported attachments using the ingestion priority order: PPT/PPTX, PDF, then DOC/DOCX.
Both paths produce the same normalized context object: generated summary, description, extracted raw text, key terms, business problem, business capability, stakeholders, and systems/products. This keeps downstream retrieval and LLM selection consistent regardless of whether the ticket contains a formal idea card.
5.3 Historical ticket retrieval
The new ticket's summary is embedded and used to retrieve the top 6 most similar historical Engagement-Request documents from idp_teg_data (the index holds only historical ER documents; it is retrieval-only, returning ranked ids whose ticket summary and resolved VS ground-truth are read from Cosmos). The 50 approved Value Streams are NOT retrieved from the index — the full governed set is supplied from the Azure SQL DB (integration pending) and passed in whole to the selection step.
5.4 Value Stream candidates
There is no candidate trimming: all 50 approved Value Streams are presented to the selection LLM, with the 6 retrieved historical tickets as precedent evidence. The model — not a pre-ranking step — decides relevance.
Note: the historic direct/implied classification step (previously applied during ingestion) was removed after an offline evaluation showed it did not improve downstream Value Stream selection accuracy.
5.5 LLM selection prompt and output
The Value Stream selection is a single LLM call. The model receives the new ticket's raw idea-card text (~24k tokens), the full 50-VS catalogue (name, description, category, trigger, value proposition and assumptions for each Value Stream), and the 6 historically similar ER tickets shown as summaries with their VS ground-truth labels. It returns the requested number of Value Stream picks (default 10) with confidence, supportType, reason, and sourceTickets (for implied picks).
Prompt inputs passed to the LLM
New ticket raw idea-card text (~24k tokens); the full 50-VS catalogue (each: name, description, category, trigger, value proposition, assumptions); the 6 historical ER tickets as summaries with their VS ground-truth labels; user count control (default 10, count-only custom instruction).
•   User control: requested number of Value Streams (default 10, exact). An optional free-text custom instruction may ONLY set this count (e.g. "give me 6"); the count is parsed deterministically and the raw text never reaches the prompt, so any non-count or malicious instruction is ignored.
•   Historical ticket evidence: the six matched Engagement Requests are shown to the user first; the selected/relevant tickets are used to strengthen historical evidence in the candidate set.
Candidate block format
Each candidate is passed as a compact block instead of a raw row. This keeps the prompt readable and makes the evidence explicit.
| Candidate: Configure, Price and Quote entity_id: VSR-#### description: <value stream description> category: Sales and Enrollment trigger: <what initiates the value stream> value: <value proposition> assumptions: <value stream assumptions> |
|---|

Selection and execution behavior
•   A single selection LLM call processes all candidates; picks are resolved to the approved catalogue and deduplicated. (A two-call split is deferred and eval-gated.)
Expected LLM output
The LLM returns a structured Value Stream selection payload. Each selected item must include:
•   valueStreamId and valueStreamName resolved to the approved catalogue.
•   confidence score, 0-100.
•   supportType: direct or implied.
•   reason explaining the business fit in plain language.
•   source tickets: included only for implied picks.
The output is exactly the requested count (default 10): after validation and dedup against the approved catalogue, the list is trimmed or padded to that number.
All LLM calls in this phase use strict structured output: the model response is constrained to a typed pydantic schema enforced by the gateway, so the candidate list, supportType, reason and confidence fields are always returned in the expected shape - no free-form parsing or post-hoc JSON repair is required.
Contract B — Request  (POST /api/vs-selection)
Request: ticketId, summaryFields (retrieval/embedding query), rawText (new ticket raw idea-card text, ~24k tok), requestedCount, customInstruction, selectedHistoricalTicketIds[].
Contract B — Response
Response: ticketId, recommendations[] each {valueStreamId, valueStreamName, confidence, supportType, reason, sourceTickets}, plus model, latencyMs.
5.6 Quality metrics for Value Stream selection
Precision is monitored on the final selected Value Streams against the curated ground-truth labels; observed range is 60-65%.
Recall is monitored against the same ground truth, observed range is 75–82% (measured at the default requested count of 10; at count = ground truth, precision = recall = F1 ≈ 0.78 — see §7).
Stage selection quality metrics
Precision is monitored on the selected stages against approved stage ground truth; observed ≈ 35%.
Recall is monitored against the same ground truth; observed ≈ 89%. The stage selector runs with no count cap (recall-first): it returns every stage the work plausibly touches and the architect trims, so recall is prioritised and precision is intentionally lower (the thin, under-tagged ground truth also understates true precision).
Latency is measured for the Value Stream LLM section end-to-end (a single selection call).
6. Theme Generation Solution
After Value Stream recommendation, a human-in-the-loop review first confirms the final Value Stream set. Theme generation starts only after this approval. Each approved Value Stream maps to one Theme package. For each approved Value Stream, the system generates the Theme title, standardized description, selected stages, Business Needs, and L2/L3 capability hierarchy using the normalized ticket context and governed catalogue data from the Azure SQL DB.

Figure 3. Theme generation flow after human approval of Value Streams.
6.1 Orchestration sequence
The sequence is approval-gated: no Theme description, stage selection, Business Needs, or capability output is generated until the SME confirms the Value Stream set. After approval, generation runs in two bands. A ticket-level band runs once for the ticket as a whole, covering all approved Value Streams together. A per-VS band then fans out, running once for each approved Value Stream. This batching is what keeps the total LLM call count roughly linear in the number of approved Value Streams instead of multiplying every call by N.
Ticket-level calls (run once, in parallel, covering all approved Value Streams - 3 calls total regardless of N):
•   Description BODY: generates the shared narrative body of the Theme Description from the ticket's raw idea-card text (see 6.2). This call is independent of any specific Value Stream and runs exactly once per ticket.
•   Description FRAMING: generates a short per-Value-Stream framing paragraph for every approved Value Stream in a single batched call, using the normalized ticket context plus the list of approved Value Streams.
•   Stage selection: predicts selectedStages for every approved Value Stream in a single batched call, using the normalized ticket context and the governed stage list for each Value Stream. Returns {stageId, stageName, reason} per selected stage; only governed catalogue stages are returned.
Per approved Value Stream (fan out, 2 calls each, in parallel across Value Streams):
•   Business Needs: explains that Value Stream's selected stages in the context of the IDMT ticket, business problem, stakeholders, and desired capability.
•   Capabilities: for that Value Stream, a single batched call selects the applicable L3 capabilities for all of its selected stages from the governed candidate L3 lists - it never invents capabilities. Each selected L3 maps one-to-one to its parent L2, so the L2 set is derived deterministically from the selected L3s; there is no separate L2 LLM call.
•   Theme title: deterministic, built from the IDMT ticket title plus the approved Value Stream name - no LLM call.
•   Theme package assembly: for each approved Value Stream, the final Theme package combines the deterministic title, the assembled description (shared body + that Value Stream's framing), Business Needs, selectedStages, and L2/L3 capabilities.
Net effect: for N approved Value Streams, the ticket-level band makes 3 calls in total and the per-VS band makes 2 calls per Value Stream, for 3 + 2N calls overall.
Each batched selection step (stages, capabilities) is followed by a deterministic salvage step that reassigns any cross-element mislink to its true owner; the strict-isolation prompt makes this rare, and the salvage guarantees a mislinked-but-valid pick is recovered rather than lost.
6.2 Context passed to each generation call
Generation input. Every theme-generation call reads the raw consolidated idea-card text (the ticket description plus extracted attachment text, consolidated and capped to ~24,000 tokens at ingest). Generation does not use the condensed summary or the generation signals - those are produced for retrieval and routing only. The same raw text is the single factual source for the theme description, business needs, stage selection, and capability selection. (Rationale: evaluation showed the raw idea card gives generation the detail it needs; the summary is the right input for retrieval, not generation.)
Stage Selection
Context:
•   One batched call covers all approved Value Streams, reading the raw idea-card text (~24k tokens)
•   Each Value Stream is matched only against its own governed candidate stages from the Azure SQL catalogue (stageId, stageName, stageDescription, entranceCriteria, exitCriteria, valueItems, stakeholders)
•   No count cap: returns every stage the work runs through, feeds, or changes (one or several) - not a "typically 1-3" quota
•   STRICT VALUE-STREAM ISOLATION: candidate lists are disjoint; only ids printed under a Value Stream may be returned for it
•   Boundary handling: when the work spans two adjacent stages, both are included
Output: one batched call returns selectedStages per approved Value Stream, each entry {stageId, stageName, reason}, resolved only against that Value Stream's governed stages. A stage placed under the wrong Value Stream is salvaged to its owning Value Stream by a deterministic post-step (a stage id belongs to exactly one Value Stream) rather than dropped. An approved Value Stream is never left empty: if no usable stages return, the full governed list is taken for the architect to trim.
Theme Description
Context:
Body call (shared, once for the ticket):
•   Reads the raw consolidated idea-card text (idmtTicketId, idmtTicketTitle, ~24k-token raw text) - no generationSignals
•   Hard grounding rule: every statement must be supported by a specific phrase in the idea card; if it cannot be pointed to, it is omitted
•   Product Availability lines (Go-live, Plans, Market Segments, Funding Model, Networks) are included only when the idea card explicitly states them - never inferred
•   Funding Model = insurance funding (ASO / FI / Commercial), not project/seed funding; Plans = states/markets, not benefit features
Framing call (batched, once for all approved Value Streams):
•   idmtTicketId, idmtTicketTitle, the raw idea-card text, and for each approved Value Stream: valueStreamId, valueStreamName, valueStreamDescription, valueProposition
•   Same grounding rule as the body call: no invented stakeholders, outcomes, or scope to fill a paragraph
•   Runs after HITL approval, in parallel with stage selection and with the body call
Output: the framing call returns a short, Value-Stream-specific intro framing this theme; the body call returns the shared narrative body, both grounded in the raw idea-card text. The two are concatenated into one consolidated, Jira-formatted Theme Description text: the framing intro, then the narrative body, then a Product Availability section populated ONLY when the idea card explicitly states it (go-live status and target states/markets - Plans here means the states/markets the offering is available in, not benefit-level plan features; insurance funding model - ASO, Fully-Insured, or Commercial, not project/seed funding; market segments; networks; product structure/pairing), then the initiative overview, key features, and optional Digital Experience / Integration-Operational sections. Product Availability values are never invented or inferred.
Business Needs
Context:
•   Approved valueStreamId, valueStreamName, valueStreamDescription, valueProposition
•   All of this Value Stream's selected stages (stageId, stageName, stageDescription)
•   The raw idea-card text (no summaryFields/generationSignals), grounded by the same hard rule: every need, dependency, and business rule must trace to a specific phrase in the idea card
•   Operational Training and Operational Reporting sub-sections are included only when the idea card explicitly describes them
•   One batched call per approved Value Stream, covering all of its selected stages together. Waits for stage selection output; runs in parallel with Capabilities (the other per-VS call). The document is structured as one "Value Stage:" block per selected stage, addressing every selected stage in scope.
Output: one consolidated Business Needs text, structured as one "Value Stage:" block per selected stage - each grouped Business Product Feature -> numbered needs, with optional Note / Dependency / Business Rule, plus Operational Training and Operational Reporting only when the idea card describes them. Every selected stage is addressed in the document; nothing is invented beyond what the idea card states.
Capabilities (L3 / L2)
Context:
•   Approved valueStreamId, valueStreamName, valueStreamDescription
•   All of this Value Stream's selected stages (stageId, stageName, stageDescription)
•   Governed candidate L3 capabilities for each selected stage (stageId, capabilityId, name, description, tier, and parent L2) - the LLM selects from these only
•   The raw idea-card text (no summaryFields/generationSignals); no count cap - include every candidate capability the work exercises, and when unsure whether a capability applies, include it
•   STRICT STAGE ISOLATION: each candidate capability is evaluated only against its own stage's scope; it is selected only if the idea card supports it for that specific stage
•   One batched call per approved Value Stream, covering all of its selected stages together. Waits for stage selection; runs in parallel with Business Needs (the other per-VS call). Followed by the deterministic salvage step (see 6.1) that reassigns any cross-stage mislink to its true owning stage. L2 is derived from the selected L3, not generated.
Output: per selected stage within the Value Stream, every L3 capability the work exercises {stageId, capabilityId, name, reason}, drawn only from that stage's governed candidates (never invented) - no count cap, and the array is never left empty without justification. Each selected L3 maps 1-1 to its parent L2; the derived L2 capability list {capabilityId, name} per Value Stream is the unique set of parents of the L3 capabilities selected across all of that Value Stream's selected stages. There is no separate L2 generation call.
6.3 Final Theme package returned for review
The phase returns one Theme package per approved Value Stream. The package remains a recommendation until the SME reviews and approves it for Jira writeback. The expected structured output contains:
•   themeTitle: deterministic title built from IDMT ticket title + Value Stream name.
•   themeDescription: standardized description narrative.
•   businessNeeds: one consolidated Business Needs text for the selected stages.
•   l3Capabilities: selected from the governed candidates; l2Capabilities: derived 1-1 from the selected L3.
Contract C — Request  (POST /api/theme-generation)
Request: ticketId, ticketTitle, condensed.rawText, approvedValueStreams[{valueStreamId, valueStreamName}].
Contract C — Response (Full Package — 6.3)
Response: themePackages[], each { valueStreamId, valueStreamName, themeTitle, themeDescription, selectedStages[{stageId, stageName, reason}], businessNeeds, l2Capabilities[ per stage ], l3Capabilities[ per stage {capabilityId, name, reason} ] }, plus model, promptVersion, latencyMs.
7. Evaluation
This section summarizes how each generation and selection component was measured during offline evaluation, and records the locked, evaluation-validated results referenced throughout this document. Full per-component analyses live in the EDA documents; this section keeps the headline method, results, key findings, and cost notes.
7.1 Method
Classification components (Value Stream, Stage, L3 capability) are scored by precision, recall and F1 against Jira ground truth, and report a coverage ceiling - the share of ground truth reachable from the governed catalogue - so a catalogue gap is not misread as a model error. Generative components (Theme Description, Business Needs) are evaluated reference-free against the source idea card, since the free-form ground-truth text is too varied to score against directly: faithfulness (claims grounded in the idea card), hallucination (1 minus faithfulness), and coverage (source key facts reflected in the output). Business Needs additionally reports stage usage (every selected stage addressed) and stage alignment (needs placed within the correct stage's scope).
7.2 Locked results
The table below reports the locked evaluation results for each component, measured on the evaluation cohort. See the per-component EDA documents for full breakdowns.
| Component | Metric | Result |
|---|---|---|
| Value Stream selection | F1 (= precision = recall at count=ground truth) | ~0.78 |
| Stage selection | F1 / recall / precision (answerable, one_call, no count cap) | ~0.50 / ~0.89 / ~0.35 |
| L3 capability selection | F1 / recall / precision (answerable, one_call) | ~0.62 / ~0.87 / ~0.48 |
| Theme Description | faithfulness / hallucination / coverage | 0.94 / 0.06 / 0.77 |
| Business Needs | faithfulness / hallucination / coverage | 0.90 / 0.10 / 0.81 |
| Business Needs (structural) | stage usage / stage alignment | 1.00 / 0.86 |

7.3 Key findings
•   The new-ticket raw prompt is the main lever for Value Stream selection; summary retrieval beats raw-embedded retrieval, so summarization stays for retrieval only.
•   For the selection components, removing the per-element count cap recovered substantial recall (the count was the limiting lever). The residual gap is largely ground-truth label noise (selections the architect made from convention, not derivable from the ticket) plus catalogue coverage gaps (ground truth tagged at theme level mapping to stages/capabilities outside the selection).
•   Cross-element mislinking is prevented by the strict-isolation prompts and corrected by the salvage layer (residual mislinking is approximately zero).
•   For the generative components, a grounding prompt rule (every claim must trace to an idea-card phrase) was the lever, trading a little completeness for far less invention - the right trade-off for an architect-facing artifact.
7.4 Cost
Each component reports per-call generation latency and token usage (prompt and completion) for capacity planning. The batched architecture keeps the per-ticket call count low: approximately 23 LLM calls for a ticket with 10 approved Value Streams and roughly 3 stages per Value Stream.
| component | avg lat | median | max | avg prompt tok | avg completion tok |
|---|---|---|---|---|---|
| Stage selection | 7.1s | 3.7s | 25.5s | 7,602 | 1,273 |
| Theme Description (body+framing) | 6.0s | 5.7s | 10.1s | 5,152 | 853 |
| L3 capability | 4.3s | 3.9s | 9.2s | 5,847 | 699 |
| Business Needs | 8.3s | 7.8s | 17.0s | 5,520 | 1,567 |

With the parallel 3 + 2N fan-out, theme generation completes in ~15s wall-clock regardless of the number of approved Value Streams (the per-VS calls run concurrently). End-to-end model time is ~27s (condense ~7s + Value Stream retrieval/selection ~5s + theme generation ~15s), excluding the human approval gate. Business Needs is the slowest component because it emits the most tokens (~1,567 completion), not from any sequential sub-call.