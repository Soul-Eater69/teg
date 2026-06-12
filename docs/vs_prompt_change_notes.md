## What changed in each prompt, and which number it moved

We compared three instruction sheets for the same setup (History + no scores). Only the prompt
wording changed; the tickets, candidates, and evidence shown to the model were identical.

### Current → Trust

The current prompt is cautious about precedent: it says "Treat them as PRECEDENT, not as answers",
"Do NOT pick a value stream solely because a past ticket used it", and in its fit test "exclude it
— even if a past ticket used it." When it ran short of the requested count, the leftover slots were
padded with arbitrary catalogue streams.

The **Trust** prompt replaced that padding with a two-tier rule: **Tier 1** = the streams that
clearly fit; **Tier 2** = fill the remaining slots with streams the most-similar past tickets were
tagged with, never random padding.

**Effect:** recall 0.726 → 0.770 and precedent backed 0.76 → 0.81 — precedent that used to be
wasted on padding now lands on real answers. Easy-ticket recall jumped to 0.94. **Cost:** judge
precision slipped (0.478 → 0.457) and it ran slower — treating precedent as a blunt count-filler
pulled in a few weak picks.

### Trust → Recall

Two wording changes. (1) Precedent moved from a fallback filler to a **primary inclusion signal**:
"PRECEDENT IS A PRIMARY SIGNAL … INCLUDE a precedent-backed stream unless it clearly cannot apply",
with an explicit priority order (process fit → precedent → upstream/downstream reach). (2) An
explicit **completeness** instruction for multi-workflow ideas: "An idea rarely touches only one
workflow … find ALL of them … under-selecting is the most common mistake."

**Effect:** hard-ticket recall 0.718 → 0.744 (the completeness push made the model enumerate the
upstream/downstream streams that multi-VS tickets need), precedent backed 0.81 → 0.83 and lift
0.34 → 0.41 (precedent first-class, not padding), and judge precision recovered to 0.470 — picks
were now justified by reasoning or a named precedent rather than dumped to fill the count.

### In short

**Trust** stopped wasting slots on random padding (lifted overall + easy recall). **Recall** then
made precedent first-class and forced multi-workflow completeness (lifted the hard cohort and
restored precision). Each change targeted a measured weak spot, and the judge-precision guardrail
confirms the gains are real picks, not count-padding.
