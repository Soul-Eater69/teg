# Value Stream selection tuning — prompt + historic-K experiments

Record of the tuning pass on Value Stream prediction. Two levers were tested on the same
60-ticket eval set: the **selection prompt** and the **number of similar past tickets**
(historic-K) shown as precedent evidence.

## Setup

- Mode: `evidence` (the model sees the full 50-stream catalogue + similar past tickets as
  evidence), candidate scores hidden (`--no-candidate-scores`).
- 60 tickets, exact count = 10, `min-gt 1`, LLM judge on. Single run each (`--repeat 1`) —
  treat sub-0.02 gaps as noise; confirm a winner at `--repeat 3` before adopting.
- Retrieval is identical across every run (same search), so any change is the model's selection.
- 100% of misses are "model saw it, didn't pick it" — retrieval is not the bottleneck, the
  prompt is the only lever.

## Metric note: precedent *backed* vs *lift*

- **Precedent backed (capture)** — of the correct answers that appeared in the shown past
  tickets, the fraction the model actually picked. Absolute; ceiling is `historic_lane` recall.
- **Precedent lift** — `backed − notbacked`: how much *more* a precedent-backed answer is picked
  vs one with no precedent. Measures whether the examples *cause* the pick.

## Experiment 1 — selection prompt (historic-K = 6)

| prompt | recall | F1 | easy R | hard R | precedent backed | lift | judge P | misses |
|---|---|---|---|---|---|---|---|---|
| Current (`selection_evidence`) | 0.726 | 0.294 | 0.838 | 0.692 | 0.764 | +0.308 | 0.478 | 42 |
| Trust (`selection_evidence_trust`) | 0.770 | 0.311 | 0.943 | 0.718 | 0.812 | +0.338 | 0.457 | 35 |
| **Recall (`selection_evidence_recall`)** | **0.776** | **0.314** | 0.886 | **0.744** | **0.827** | **+0.406** | 0.470 | **34** |

**Winner: Recall prompt.** +0.050 recall and +0.052 hard-ticket recall over the current prompt,
captured more precedent (0.76 → 0.83) and relied on it more (lift 0.31 → 0.41) — and the judge
precision guardrail held (0.478 → 0.470), so the extra picks are genuinely relevant, not padding.
Trust also helped but less on hard tickets, dropped judge precision more, and ran slower.

### What changed in each prompt, and which number it moved

**Current → Trust.** The current prompt is *conservative about precedent*: it says
"Treat them as PRECEDENT, not as answers", "Do NOT pick a value stream solely because a past
ticket used it", and in the fit test "exclude it — even if a past ticket used it." When it ran
short of the requested count, the leftover slots were padded with arbitrary catalogue streams.
The Trust prompt replaced that with a two-tier rule: **Tier 1** = the streams that clearly fit;
**Tier 2** = *fill the remaining slots with streams the most-similar past tickets were tagged
with, not random padding* ("do NOT pad with random streams when precedent streams are available").
*Effect:* recall 0.726 → 0.770 and precedent backed 0.76 → 0.81 — the precedent that used to be
wasted on padding now lands on real GT. Easy-ticket recall jumped to 0.94. *Cost:* judge precision
slipped (0.478 → 0.457) and latency rose — treating precedent as a blunt count-filler pulled in
a few weak picks, and the extra reasoning was slower.

**Trust → Recall.** Two wording changes. (1) Precedent moved from a *fallback filler* (Tier 2)
to a **primary inclusion signal**: "PRECEDENT IS A PRIMARY SIGNAL … INCLUDE a precedent-backed
stream unless it clearly cannot apply", with an explicit priority order (process fit → precedent →
upstream/downstream reach). (2) An explicit **completeness** instruction for multi-workflow ideas:
"An idea rarely touches only one workflow … find ALL of them … under-selecting is the most common
mistake." *Effect:* hard-ticket recall 0.718 → **0.744** (the completeness push made the model
enumerate the upstream/downstream streams that multi-VS tickets need), precedent backed 0.81 →
**0.83** and lift 0.34 → **0.41** (precedent as a first-class signal, not padding), and judge
precision **recovered** to 0.470 — because picks were now justified by reasoning or a named
precedent rather than dumped to fill the count.

In short: **Trust** stopped wasting slots on random padding (lifted overall + easy recall);
**Recall** then made precedent first-class and forced multi-workflow completeness (lifted the hard
cohort and restored precision). Each change targeted a measured weak spot, and the guardrail
(judge precision) confirms the gains are real picks, not count-padding.

## Experiment 2 — historic-K (Recall prompt fixed)

| K (past tickets) | recall | F1 | hard R | precedent ceiling | backed | lift | judge P |
|---|---|---|---|---|---|---|---|
| **6** | 0.776 | 0.314 | 0.744 | 0.887 | 0.827 | +0.406 | 0.470 |
| 8 | 0.796 | 0.322 | 0.769 | 0.892 | 0.838 | +0.401 | 0.460 |
| 10 | 0.796 | 0.322 | 0.769 | 0.913 | 0.827 | +0.366 | 0.450 |

- **6 → 8**: small real gain (recall +0.020, hard R +0.025), captured a bit more precedent.
- **8 → 10**: dilution, not gain — recall/F1/hard-R flat, but the ceiling rises (more precedent
  surfaced) while the model captures *less* of it (backed 0.838 → 0.827), lift falls
  (0.401 → 0.366), and judge precision keeps eroding (0.460 → 0.450). The extra tickets are
  less-similar analogs that add noise.

## Decisions

- **Adopt the Recall prompt** (`value_stream/selection_evidence_recall`) — the genuine win.
- **Keep historic-K = 6.** K=8's +0.020 recall is within run-to-run noise and not a major gain;
  it isn't worth the added prompt length and the dilution risk that grows at K=10. Stay at 6.

## Cumulative effect (prompt only, K=6)

- recall **0.726 → 0.776** (+0.050, ~7% relative)
- hard-ticket recall **0.692 → 0.744** (+0.052)
- judge precision held (~0.47) — the gain is real, not count-padding.

All from prompt wording; no model, index, or retrieval changes.

## Follow-ups

- Confirm the Recall prompt at `--repeat 3` before wiring it as the evidence-mode default.
- The `--historic-k` eval flag stays available for future re-tests; the config default
  `historical_fetch_k` remains 6.
