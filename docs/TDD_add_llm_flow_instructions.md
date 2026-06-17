# TDD instructions — add the "LLM invocation flow" overview

**For:** the coworker maintaining the TDD.
**Goal:** add a single system-overview figure + short rationale that shows, for the whole pipeline,
**where an LLM is invoked, where it is not, and why** (i.e. that the design is lean, not brute force).

**Assets I've prepared (use these — do not redraw):**
- Diagram image: **`docs/flow_charts/master_flow.png`** (also on the Desktop as `master_flow.png`).
- Full reference write-up (source of the text below): `docs/llm_invocation_flow.md`.

---

## Where to put it

Add a new short subsection at the **end of §1 Executive Summary** (or as a new **§1.1 System Overview**),
before §2. It belongs up front because it frames the whole document.

Heading: **"1.1 System overview — where an LLM is invoked (and where it is not)"**

## What to add

**1. One intro sentence:**
> *An LLM is invoked only where the task is irreducibly semantic — judgment or generation that no lookup,
> rule, or index can do. Everything mechanical (parsing, token packing, id routing, dedup, templating,
> vector search) stays deterministic code. The diagram below marks each step by kind.*

**2. Insert the figure** `master_flow.png` with caption:
> *Figure 0. End-to-end flow. Orange = LLM call (semantic judgment/generation); blue = embedding /
> vector retrieval (a model, not a generation call); grey = deterministic code; gold = human gate.*

**3. Add this "kinds of step" table:**

| colour | kind | examples |
|---|---|---|
| orange | LLM call — judgment / generation | Condense, VS Selection, Stage Selection, Description, Business Needs, Capabilities |
| blue | embedding / retrieval (not a generation call) | top-6 historical vector search |
| grey | deterministic — no model | assembly, L2 derivation, salvage, title, token packing |
| gold | human gate | HITL approval |

**4. Add the call-count line:**
> *For N approved Value Streams, one new ticket costs **5 + 2N LLM calls** (Condense 1, VS Selection 1,
> Stage Selection 1, Description body+framing 2, then Business Needs + Capabilities 1 each per VS), plus
> one embedding call for retrieval. Retrieval, catalogue load, L2 derivation, salvage, title, and
> assembly use no generation call.*

**5. (Optional but recommended) the "why no LLM here" callouts** — a short list showing the design is
deliberate, not brute force:
> - **L2 derivation** — each L3 has exactly one parent L2, so L2 = the unique parents of the selected
>   L3s (a lookup). An LLM would pay to reproduce a fact we compute exactly.
> - **Ground-truth extraction** — the BA's answer is already in the Jira VS-Stage field; an LLM would
>   fabricate labels we already have authoritatively.
> - **Salvage** — a stage/capability id is globally unique to one owner, so a mislink is re-routed by an
>   id→owner map, not a second LLM.
> - **Retrieval** — "find similar" is nearest-neighbour search (cheaper and more accurate than an LLM
>   scanning the corpus).

---

## Consistency notes (so this figure agrees with the rest of the TDD)

- This figure shows **Condense = LLM ×1** (the locked design; the dropped "signals" pass is not counted).
  Keep it ×1 to match §5.1.
- Theme-gen counts here are **5 + 2N** — consistent with §6.1's `3 + 2N` *theme-generation* calls plus
  the upstream Condense + VS Selection. (Don't "correct" one to the other: §6.1 counts only the
  theme-generation band; Figure 0 counts the whole pipeline.)
- Colours / wording match Figures 1–3 already in the doc (orange LLM, green/grey deterministic, gold gate).

## Checklist
- [ ] New §1.1 (or end of §1) added with the intro sentence.
- [ ] `master_flow.png` inserted as **Figure 0** with the caption.
- [ ] "kinds of step" table + the `5 + 2N` call-count line present.
- [ ] (optional) the four "why no LLM" callouts added.
- [ ] Condense shown as ×1; no contradiction with §5.1 / §6.1.
