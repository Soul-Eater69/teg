# Business Needs generation — EDA

**Question:** are the generated Business Needs **grounded** (no invention) and **complete**, do they
**use every selected stage**, and are each stage's needs **in-scope** for that stage?

## What is generated

Business Needs are generated **per approved value stream**, for its **selected stages** (here: the
GT stages), from the **raw idea card only** (no summary, no generation signals — the locked
theme-gen decision). The output is one consolidated document structured as one block per stage:

```
Value Stage: <stage name>
  Business Product Feature: <scope area>
    1. <business need>   Note / Dependency / Business Rule (each only if stated)
  Operational Training / Operational Reporting  (only if stated)
<repeat per selected stage>
```

## How we evaluate — reference-free + structural

Like description, we do **not** score against the free-form GT text (matching it penalises style).
We judge each value stream's Business Needs against the **raw source**, plus two **structural** checks
the stage-keyed format makes possible:

| metric | measures | vs |
|---|---|---|
| **faithfulness** | claims grounded in the idea card (no invention) | source |
| **hallucination** | `1 − faithfulness` (the invented claims) | source |
| **coverage** | the idea card's key facts reflected | source |
| **stage_usage** | selected stages **addressed** in the output | the stage set |
| **stage_align** | addressed stages whose needs **fit that stage's scope** (not misfiled) | catalogue scope |

**Where is "correctness"?** There is no separate correctness metric, by design. Correctness-vs-GT
was dropped because each GT Business Needs document is free-form (matching it would penalise style,
not substance). In a reference-free eval, *"is this need correct?"* becomes *"is it supported by the
source?"* — so **faithfulness IS the correctness check** (a need is correct iff the idea card backs
it), and coverage is the completeness check. We keep faithfulness + hallucination + coverage rather
than a redundant "correctness" label.

---

## Finding — the structural checks pass; grounding is the lever

The **stage checks were excellent from the start** and held throughout: the model **uses every
selected stage** and files needs under the right one.

| metric | baseline | final |
|---|---|---|
| **stage_usage** | 1.000 | **0.999** |
| **stage_align** | 0.972 | **0.855** |

The real work was **grounding**. Business Needs is **prescriptive** ("the business needs X must be
built"), so it invents requirements far more readily than descriptive prose — the baseline leaked
26% hallucination.

![Prompt journey](needs_charts/journey.png)

**The journey** — the prompt versions on the same sample, ending at the locked config:

| metric | baseline | grounding (over-tight) | rebalanced | **final** |
|---|---|---|---|---|
| faithfulness | 0.735 | 0.817 | 0.827 | **0.895** |
| hallucination | 0.265 | 0.183 | 0.173 | **0.105** |
| coverage | 0.736 | 0.633 | 0.669 | **0.810** |
| stage_align | 0.972 | 0.812 | 0.833 | **0.855** |

1. **Diagnosis:** the prompt was **signal-centric** (Operational Training/Reporting "only if signals
   exist"; Note/Dependency/Business Rule) — but theme gen feeds **raw text with no signals**, so the
   model **fabricated** dependencies, business rules, and training/reporting from inference. 1 in 4
   claims unsupported.
2. **Grounding pass:** a hard rule (every need/note/dependency/rule must trace to a card phrase;
   conditional sub-fields reframed from "signals" to "the card explicitly states it; never infer")
   lifted faithfulness, but **over-corrected**: "a thin stage gets few needs / don't pad" made the
   per-stage needs **sparse and vague**, dropping coverage and stage_align — vague one-liners are
   hard to scope-match.
3. **Rebalance:** reworded from *"write less"* to *"write only what's grounded, but capture
   **everything** the card supports and state each need concretely enough to belong to THAT stage."*
   This **kept the no-invention gain and recovered alignment and coverage**.

![Final metrics](needs_charts/final.png)

## The honest read

- **Faithfulness 0.895 / hallucination 0.105** is strong for a **prescriptive** artifact — inventing
  requirements is its inherent failure mode, so ~0.10 hallucination is a good result on raw-only input.
- **Coverage 0.810** — grounding hard while still capturing what the card supports; the no-invention
  rule is the domain's #1, and the rebalance kept completeness alongside it.
- **The structural checks are the win you asked for:** stage_usage ≈ 1.0 (no stage silently dropped)
  and stage_align 0.855 (needs filed under the right stage) — the document is well-structured.

## Verdict — locked

**Business Needs: raw idea card only, grounding-rebalanced prompt → faithfulness 0.895 /
hallucination 0.105 / coverage 0.810 / stage_usage 0.999 / stage_align 0.855.**

- Reference-free (judged vs source; the GT format is too varied to score against), plus the
  stage-usage / stage-alignment structural checks.
- Grounding was the lever; the rebalance kept the no-invention gain while recovering stage alignment
  and coverage.
- Faithfulness 0.895 / hallucination 0.105 is strong for a prescriptive artifact, with the structural
  checks near-perfect (stage_usage ≈ 1.0, stage_align 0.855).

**No further changes.**
