# Prompt input/output reference — every LLM call, with the filled-in prompt

Each LLM call in the current design, in pipeline order. For each: a one-line note on what the system
prompt instructs, the **filled-in prompt the model actually receives** (template variables substituted
with real data), and the **output** (typed structured-output schema + example). All generation calls
read the **raw text** — no generation signals. The output schema is passed to the gateway as structured
output, never as a JSON block inside the prompt.

Running example: **IDMT-19761 — "Enabling Real-Time Quote Automation for Enterprise Accounts."** Sales
Operations needs a real-time CPQ integration to cut the enterprise quote cycle from five days to
same-day; discounts above 20% require VP approval; accepted quotes hand off to order fulfilment within a
4-hour Deal Desk SLA.

---

## 1. Condense  (LLM ×1, per ticket)

**System:** extract structured context from the ticket source in one pass; return the summary fields.

**Filled prompt (user message):**
```
Ticket ID: IDMT-19761

Source material:
[Idea card] Enabling Real-Time Quote Automation for Enterprise Accounts. Sales Operations needs a
real-time CPQ integration so enterprise quotes go out same-day instead of taking 3-5 days. Pricing
must come live from Oracle ERP via Salesforce CPQ. Discounts above 20% must route to VP approval.
Accepted quotes hand off to order fulfilment; the Deal Desk SLA target is 4 hours.
[Attachment: business_case.pdf] ...
```
*(`Source material` is the full ~24k-token raw text.)*

**Output** — `SummaryFields`:
```json
{
  "generatedSummary": "Sales Operations needs a real-time CPQ integration to cut the enterprise quote cycle from five days to same-day, with automated discount approval and a handoff to order fulfilment.",
  "businessProblem": "Manual quoting delays enterprise deal closures by 3-5 days.",
  "businessCapability": "Automated real-time quote generation for enterprise accounts.",
  "keyTerms": ["CPQ", "quoting", "enterprise", "Salesforce", "Deal Desk"],
  "stakeholders": ["Sales Ops", "IT", "Finance"],
  "systemsAndProducts": ["Salesforce CPQ", "Oracle ERP", "Deal Desk Portal"]
}
```

---

## 2. Value Stream Selection  (LLM ×1, per ticket)

**System:** pick the relevant Value Streams from the candidates; weigh the new ticket's raw text against
the similar past tickets; return exactly the requested count with a reason and support type.

**Filled prompt (user message):**
```
IDEA CARD SUMMARY:

Sales Operations needs a real-time CPQ integration so enterprise quotes go out same-day instead of
taking 3-5 days. Pricing comes live from Oracle ERP via Salesforce CPQ. Discounts above 20% route to
VP approval. Accepted quotes hand off to order fulfilment; Deal Desk SLA target is 4 hours.
[...full raw text...]

REQUESTED VALUE STREAM COUNT (exact):
10

SIMILAR PAST TICKETS (evidence - the value streams these were tagged with):
- IDMT-17432: CPQ enhancements for the large Deal Desk; automated pricing configuration for enterprise tiers.
  -> tagged value streams: Configure, Price and Quote (VSR-0042), Order Management (VSR-0017)
- IDMT-16890: Order fulfilment integration with CPQ; quote-to-order handoff latency reduction.
  -> tagged value streams: Order Management (VSR-0017)

CANDIDATE VALUE STREAMS:

Candidate: Configure, Price and Quote
entity_id: VSR-0042
description: Initiate, price and issue enterprise quotes.
category: Sales and Enrollment
trigger: A qualified enterprise opportunity needs a quote.
value: Faster, accurate quotes that shorten the sales cycle.
assumptions: Pricing is sourced from the master pricing system.

Candidate: Order Management
entity_id: VSR-0017
description: Capture and fulfil enterprise orders.
category: Fulfilment
trigger: An accepted quote becomes an order.
value: Reliable, on-time order fulfilment.
assumptions: Orders originate from approved quotes.

[... 48 more candidate blocks, all 50 governed Value Streams ...]
```

**Output** — `recommendations[]`:
```json
{
  "recommendations": [
    { "valueStreamId": "VSR-0042", "valueStreamName": "Configure, Price and Quote", "confidence": 91,
      "supportType": "direct", "reason": "Ticket explicitly targets CPQ automation for enterprise quoting.", "sourceTickets": [] },
    { "valueStreamId": "VSR-0017", "valueStreamName": "Order Management", "confidence": 74,
      "supportType": "implied", "reason": "Quote-to-order handoff implied by the fulfilment requirement.", "sourceTickets": ["IDMT-16890"] }
  ]
}
```

*Human approval gate — the SME confirms the Value Stream set before any generation runs.*

---

## 3. Stage Selection  (LLM ×1, all Value Streams batched)

**System:** for every approved Value Stream, select which of its governed stages the work touches; pick
only ids printed under that Value Stream; no count cap.

**Filled prompt (user message):**
```
## Ticket context
- ideaCard: Sales Operations needs real-time CPQ so enterprise quotes go out same-day; pricing live
  from Oracle ERP via Salesforce CPQ; discounts >20% need VP approval; accepted quotes hand off to
  order fulfilment within a 4-hour SLA.
- businessProblem: Manual quoting delays enterprise deal closures by 3-5 days.
- businessCapability: Automated real-time quote generation for enterprise accounts.
- keyTerms: CPQ, quoting, enterprise, Salesforce, Deal Desk
- stakeholders: Sales Ops, IT, Finance
- systemsAndProducts: Salesforce CPQ, Oracle ERP, Deal Desk Portal

## Approved value streams (each with its own candidate stages)
### Value Stream VSR-0042 — Configure, Price and Quote
[1] Opportunity to Quote (VSS-0042-01)
description: Initiate and price an enterprise quote.
entrance: opportunity qualified | exit: quote issued
[2] Quote to Order (VSS-0042-02)
description: Convert an accepted quote into an order.
entrance: quote accepted | exit: order created
[3] Quote Revision (VSS-0042-03)
description: Revise an issued quote on customer request.
entrance: revision requested | exit: revised quote issued

### Value Stream VSR-0017 — Order Management
[1] Order Capture (VSS-0017-01)
description: Receive and validate the enterprise order.
entrance: order requested | exit: order validated
...
```

**Output** — one entry per Value Stream, keyed by id:
```json
{
  "value_streams": [
    { "valueStreamId": "VSR-0042", "selectedStages": [
        { "stageId": "VSS-0042-01", "stageName": "Opportunity to Quote", "reason": "Ticket targets the quoting initiation workflow." },
        { "stageId": "VSS-0042-02", "stageName": "Quote to Order", "reason": "Quote-to-order handoff is in scope." } ] },
    { "valueStreamId": "VSR-0017", "selectedStages": [
        { "stageId": "VSS-0017-01", "stageName": "Order Capture", "reason": "Accepted quotes are captured as orders." } ] }
  ]
}
```
*A stage placed under the wrong Value Stream is salvaged to its owner. An empty list means "take the
whole governed list for the architect to trim."*

---

## 4. Description BODY  (LLM ×1, per ticket, VS-agnostic)

**System:** write the shared narrative body; every statement must trace to a phrase in the raw text;
optional availability/plan lines only when the text explicitly states them.

**Filled prompt (user message):**
```
Ticket context:
- ideaCard: Sales Operations needs real-time CPQ so enterprise quotes go out same-day; pricing live
  from Oracle ERP via Salesforce CPQ; discounts >20% need VP approval; accepted quotes hand off to
  order fulfilment within a 4-hour SLA.
- businessProblem: Manual quoting delays enterprise deal closures by 3-5 days.
- businessCapability: Automated real-time quote generation for enterprise accounts.
- keyTerms: CPQ, quoting, enterprise, Salesforce, Deal Desk
- stakeholders: Sales Ops, IT, Finance
- systemsAndProducts: Salesforce CPQ, Oracle ERP, Deal Desk Portal
```

**Output** — `{ text }`:
```
This theme automates enterprise quoting by integrating Salesforce CPQ with live Oracle ERP pricing,
cutting the quote cycle from five days to same-day. Discounts above 20% route to VP approval, and
accepted quotes hand off to order fulfilment within the Deal Desk's 4-hour SLA.
```

---

## 5. Description FRAMING  (LLM ×1, all Value Streams batched)

**System:** write one short intro paragraph per approved Value Stream; same grounding rule as the body.

**Filled prompt (user message):**
```
Ticket context:
- ideaCard: Sales Operations needs real-time CPQ so enterprise quotes go out same-day ... (as above)
- businessProblem: Manual quoting delays enterprise deal closures by 3-5 days.
- ...

Approved value streams:
- valueStreamId: VSR-0042
  valueStreamName: Configure, Price and Quote
  valueStreamDescription: Initiate, price and issue enterprise quotes.
  valueProposition: Faster, accurate quotes that shorten the sales cycle.
- valueStreamId: VSR-0017
  valueStreamName: Order Management
  valueStreamDescription: Capture and fulfil enterprise orders.
  valueProposition: Reliable, on-time order fulfilment.
```

**Output** — `framings[]`:
```json
{
  "framings": [
    { "valueStreamId": "VSR-0042", "text": "Within Configure, Price and Quote, this initiative makes enterprise quoting real-time and rule-driven." },
    { "valueStreamId": "VSR-0017", "text": "For Order Management, it ensures accepted quotes flow cleanly into fulfilment." }
  ]
}
```
*Final per-VS description = its framing paragraph + the shared body, concatenated deterministically.*

---

## 6. Business Needs  (LLM ×1 per Value Stream)

**System:** write the consolidated Business Needs for one Value Stream's selected stages; every need,
dependency and rule must trace to a phrase in the raw text; one "Value Stage:" block per stage.

**Filled prompt (user message):**
```
## Approved value stream
ID: VSR-0042
Name: Configure, Price and Quote
Description: Initiate, price and issue enterprise quotes.
Value proposition: Faster, accurate quotes that shorten the sales cycle.

## Selected stages (write needs for these stages only)
[1] Opportunity to Quote (VSS-0042-01)
description: Initiate and price an enterprise quote. entrance: opportunity qualified | exit: quote issued
[2] Quote to Order (VSS-0042-02)
description: Convert an accepted quote into an order. entrance: quote accepted | exit: order created

## Ticket context
- ideaCard: Sales Operations needs real-time CPQ so enterprise quotes go out same-day ... (as above)
- businessProblem: Manual quoting delays enterprise deal closures by 3-5 days.
- ...
```

**Output** — `{ text }` (one consolidated document):
```
Value Stage: Opportunity to Quote

Business Product Feature: Real-Time Quoting
1. Sales Operations requires real-time quote generation to replace the current 3-5 day manual cycle.
   Dependency: Salesforce CPQ and the Oracle pricing API.
   Business Rule: Discounts above 20% require VP approval.

Value Stage: Quote to Order

Business Product Feature: Order Handoff
1. Accepted quotes must hand off to order fulfilment within the Deal Desk 4-hour SLA.
```

---

## 7. Capabilities (L3)  (LLM ×1, ALL Value Streams merged)

**System:** for each stage, select the applicable L3 from THAT stage's own candidate list; strict stage
isolation; the same id/name repeats across stages and Value Streams — match the exact printed id only.
**L2 is derived 1-1 from the selected L3 — no separate L2 call.**

**Filled prompt (user message):**
```
## Ticket context
- ideaCard: Sales Operations needs real-time CPQ so enterprise quotes go out same-day ... (as above)
- businessProblem: Manual quoting delays enterprise deal closures by 3-5 days.
- ...

## Approved value streams, each with its selected stages and each stage's own candidate L3
### Value Stream VSR-0042 — Configure, Price and Quote
description: Initiate, price and issue enterprise quotes.

### Stage VSS-0042-01
[1] Opportunity to Quote (VSS-0042-01)
description: Initiate and price an enterprise quote. entrance: opportunity qualified | exit: quote issued
Candidate L3 capabilities (choose by id; each shows its parent L2):
- L3-0042-0011 | Real-Time Pricing Engine Integration - live CPQ pricing feed [tier: core] (L2: Pricing and Discounting)
- L3-0042-0012 | Automated Discount Approval Workflow - routes discounts for approval (L2: Approval and Governance)

### Stage VSS-0042-02
[2] Quote to Order (VSS-0042-02)
description: Convert an accepted quote into an order. entrance: quote accepted | exit: order created
Candidate L3 capabilities (choose by id; each shows its parent L2):
- L3-0042-0021 | Order Handoff Orchestration - passes the quote to fulfilment (L2: Order Management)

### Value Stream VSR-0017 — Order Management
description: Capture and fulfil enterprise orders.

### Stage VSS-0017-01
[1] Order Capture (VSS-0017-01)
description: Receive and validate the enterprise order. entrance: order requested | exit: order validated
Candidate L3 capabilities (choose by id; each shows its parent L2):
- L3-0017-0011 | Order Intake Automation - captures order data (L2: Order Management)
```

**Output** — keyed by stageId (re-attributed to each Value Stream afterward):
```json
{
  "stages": [
    { "stageId": "VSS-0042-01", "capabilities": [
        { "capabilityId": "L3-0042-0011", "capabilityName": "Real-Time Pricing Engine Integration", "reason": "Live CPQ pricing feed from Oracle ERP." },
        { "capabilityId": "L3-0042-0012", "capabilityName": "Automated Discount Approval Workflow", "reason": "Discounts above 20% require VP approval." } ] },
    { "stageId": "VSS-0042-02", "capabilities": [
        { "capabilityId": "L3-0042-0021", "capabilityName": "Order Handoff Orchestration", "reason": "Accepted quotes hand off to fulfilment." } ] },
    { "stageId": "VSS-0017-01", "capabilities": [
        { "capabilityId": "L3-0017-0011", "capabilityName": "Order Intake Automation", "reason": "Captures the order on quote acceptance." } ] }
  ]
}
```
*Strict isolation + salvage keep each L3 under its owning stage. **L2** = the unique parent L2s of the
selected L3, derived per Value Stream (here: Pricing and Discounting, Approval and Governance, Order
Management).*

---

## Final Theme package (deterministic — no LLM)

One package per approved Value Stream, assembled from the calls above:
```json
{
  "themeTitle": "Enabling Real-Time Quote Automation -- Configure, Price and Quote",
  "themeDescription": "<framing + body>",
  "selectedStages": [ { "stageId": "VSS-0042-01", "stageName": "Opportunity to Quote", "reason": "..." } ],
  "businessNeeds": "<consolidated text>",
  "l3Capabilities": [ { "stageId": "VSS-0042-01", "capabilities": [ ... ] } ],
  "l2Capabilities": [ { "stageId": "VSS-0042-01", "capabilities": [ { "capabilityId": "L2-0042-001", "name": "Pricing and Discounting" } ] } ]
}
```

---

# Evaluation judges (eval-only, reference-free)

These never run in production. They judge a generated artifact against its **source** (the raw text),
not ground truth. Claim extraction runs once and its claims feed both faithfulness and correctness.

## J1. Claim extraction  ·  `judges/claim_extraction`

**Filled prompt (user message):**
```
GENERATED TEXT:
This theme automates enterprise quoting by integrating Salesforce CPQ with live Oracle ERP pricing,
cutting the quote cycle from five days to same-day. Discounts above 20% route to VP approval, and
accepted quotes hand off to order fulfilment.

List every atomic factual claim.
```
**Output** — `ClaimList`:
```json
{ "claims": [
  "The integration cuts the enterprise quote cycle from five days to same-day",
  "Discounts above 20% route to VP approval",
  "Accepted quotes hand off to order fulfilment" ] }
```

## J2. Faithfulness / hallucination  ·  `judges/faithfulness`

**Filled prompt (user message):**
```
SOURCE:
Sales Operations needs real-time CPQ so enterprise quotes go out same-day; discounts >20% need VP
approval; accepted quotes hand off to order fulfilment. [...raw text...]

CLAIMS:
- The integration cuts the enterprise quote cycle from five days to same-day
- Discounts above 20% route to VP approval
- The feature launches in Q3

Return each claim with its supported flag.
```
**Output** — `FaithfulnessResult` (faithfulness = supported/total; hallucination = 1 − it):
```json
{ "claims": [
  { "claim": "The integration cuts the enterprise quote cycle from five days to same-day", "supported": true },
  { "claim": "Discounts above 20% route to VP approval", "supported": true },
  { "claim": "The feature launches in Q3", "supported": false } ] }   // -> faithfulness 0.67
```

## J3. Correctness  ·  `judges/correctness`

Same filled shape as faithfulness (`SOURCE` + `CLAIMS`), but checks accuracy/no-distortion.
**Output** — `CorrectnessResult` (correct/total):
```json
{ "claims": [
  { "claim": "Discounts above 20% require VP approval", "correct": true },
  { "claim": "All discounts require VP approval", "correct": false } ] }   // scope distorted
```

## J4. Coverage  ·  `judges/coverage`

**Filled prompt (user message):**
```
SOURCE:
Sales Operations needs real-time CPQ ... cut quote cycle from 5 days to same-day; accepted quotes
hand off to fulfilment. [...raw text...]

GENERATED ARTIFACT:
This theme automates enterprise quoting ... cutting the quote cycle to same-day.

Extract the source's key facts and return each with whether the generated artifact covers it.
```
**Output** — `CoverageResult` (covered/total):
```json
{ "facts": [
  { "fact": "Cut quote cycle from 5 days to same-day", "covered": true },
  { "fact": "Hand off accepted quotes to fulfilment", "covered": false } ] }   // -> coverage 0.5
```

## J5. Stage usage (Business Needs only)  ·  `judges/stage_usage`

**Filled prompt (user message):**
```
SELECTED STAGES (with their scope):
[1] Opportunity to Quote (VSS-0042-01)  description: Initiate and price a quote. entrance: ... | exit: quote issued
[2] Quote to Order (VSS-0042-02)        description: Convert an accepted quote into an order. ...

BUSINESS NEEDS DOCUMENT:
Value Stage: Opportunity to Quote ... Value Stage: Quote to Order ...

For each selected stage, return addressed + aligned + a short note.
```
**Output** — `StageUsageResult` (usage = addressed/selected; alignment = aligned/addressed):
```json
{ "stages": [
  { "stageId": "VSS-0042-01", "addressed": true, "aligned": true, "note": "Real-time quoting needs are in scope." },
  { "stageId": "VSS-0042-02", "addressed": true, "aligned": false, "note": "An order-creation need is filed here but belongs to a later stage." } ] }
```
