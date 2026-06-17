# TDD instructions — add a short client-facing "How it works" overview

**For:** the coworker maintaining the TDD.
**Why:** the client wants to understand the flow at a glance — *why there are several LLM calls and why
each is needed* — before the technical detail. This adds **one short overview**, kept minimal. **No
schema, no contracts, no field lists.**

**Asset (use as-is — do not redraw):** `docs/flow_charts/flow_overview.png` (also on the Desktop as
`flow_overview.png`). It's a clean 6-step picture with a one-line "why" beside each LLM call.

---

## Where
Add as the **first subsection of §1 — "1.1 How it works (overview)"**, right after the Executive Summary
paragraph. It is the client's entry point; the detailed sections (§3–§6) stay as they are.

## What to add — keep it to this, nothing more

**1. The picture:** insert `flow_overview.png` as **Figure 0** with caption:
> *Figure 0. The flow at a glance — where the system uses an LLM and where it doesn't.*

**2. One short paragraph (why the LLM calls):**
> *The tool mirrors what a Business Architect does by hand. It uses an LLM only for the parts that are
> genuine judgment or writing — understanding a messy idea card, deciding which business areas
> (Value Streams) a change touches, and drafting each Theme's description, needs and capabilities.
> Everything mechanical — searching for similar past work, and stitching the final package together —
> runs automatically with no LLM. A person approves the Value Streams before anything is written.*

**3. One line on the count (so "many calls" has context):**
> *So a single request makes a small, fixed set of LLM calls: one to understand the ticket, one to
> choose the Value Streams, then a few to write each approved Theme — not a brute-force sweep. Each call
> maps to one decision a Business Architect would otherwise make manually.*

**That's the whole section** — picture + two short paragraphs. Do **not** add the stage tables, the
`5 + 2N` formula, schemas, or contract shapes here; those belong to the detailed sections.

---

## Notes
- This replaces the need for the denser "end-to-end" / "LLM invocation" overviews **for the client**.
  If you already added those (the `master_flow.png` figure), keep them for the *engineering* audience but
  put **this** one first — it's the one the client reads.
- Tone is plain-business, not technical: "Value Streams", "Themes", "judgment vs mechanical" — no
  internal terms (no rawText, summaryFields, salvage, embeddings) in this section.

## Checklist
- [ ] §1.1 added with `flow_overview.png` (Figure 0) + the two short paragraphs.
- [ ] No schema / contract / field list / formula in this section.
- [ ] Placed before the technical sections; plain-business wording.
