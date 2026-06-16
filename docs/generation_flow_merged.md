# Generation flow — batching optimisations: cost & impact analysis

![Generation flow (merged Capabilities)](flow_charts/generation_flow_merged.png)

GPT-5-mini pricing throughout: **$0.25 / 1M input, $2.00 / 1M output.**

## Baseline cost — current architecture (all per-VS), 10 Value Streams

**Average tokens** (the measured sample's idea cards sit below the 24k cap):

| call | runs | input | output | cost |
|---|---|---:|---:|---:|
| Condense | 1 | 6,000 | 500 | $0.0025 |
| Choose Value Streams | 1 | 12,000 | 1,500 | $0.0060 |
| Stage Selection | 1 | 7,602 | 1,273 | $0.0044 |
| Description BODY + FRAMING | 2 | 10,304 | 1,706 | $0.0060 |
| Business Needs | 10 | 55,200 | 15,670 | $0.0451 |
| Capabilities (L3) | 10 | 58,470 | 6,990 | $0.0286 |
| **Total (average)** | **25 calls** | | | **$0.093** |

**24k worst case** — every call carries the full 24k raw idea-card text:

| call | runs | input | output | cost |
|---|---|---:|---:|---:|
| Condense | 1 | 24,000 | 500 | $0.0070 |
| Choose Value Streams | 1 | 30,000 | 1,500 | $0.0105 |
| Stage Selection | 1 | 26,600 | 1,273 | $0.0092 |
| Description BODY + FRAMING | 2 | 48,400 | 1,706 | $0.0155 |
| Business Needs | 10 | 245,200 | 15,670 | $0.0926 |
| Capabilities (L3) | 10 | 248,500 | 6,990 | $0.0761 |
| **Total (24k)** | **25 calls** | | | **$0.211** |

So the baseline is **$0.093/ticket average, $0.211 worst case** (10 VS).

---

## The changes and how they impacted quality

### Merged Capabilities (L3) — all Value Streams in one call

| metric | per-VS | merged |
|---|---|---|
| precision | 0.53 | 0.43 |
| recall | 0.90 | 0.84 |
| F1 | 0.67 | 0.57 |
| mislink in output (after salvage) | 0 | 0 |
| hallucinated ids | 0% | 0% |

Recall −6, strict precision −10 (much of which is plausible picks the ground truth didn't tag, not real
error). Nothing hallucinated; mislink is 0 in the output either way. **Quality holds up well** — L3 is
short *selection*, which batches cleanly.

### Batched Business Needs — a few Value Streams per call

| metric | per-VS | batched |
|---|---|---|
| faithfulness | 0.895 | 0.715 |
| hallucination | 0.105 | 0.285 |
| coverage | 0.810 | 0.519 |

Faithfulness −18, coverage −29, hallucination +18. **Quality degrades materially.** Business Needs is
long-form *writing*: the batched call emits **~920 output tokens per VS vs 1,567 per-VS** — each
document is ~40% shorter, so it reflects fewer source facts and grounds fewer claims. The shorter output
is the direct cause.

---

## Cost comparison 1 — merged Capabilities (whole flow, 10 VS)

| | baseline (per-VS) | merged Capabilities |
|---|---:|---:|
| LLM calls | 25 | **16** |
| cost — average | $0.093 | **$0.082** |
| cost — 24k worst case | $0.211 | **$0.157** |

Capabilities collapses from 10 calls to 1: **9 fewer calls**, **−12% cost average**, **−26% at 24k**
(the raw text is sent once instead of 10 times — the saving grows with idea-card size).

## Cost comparison 2 — batched Business Needs (whole flow, 10 VS)

| | baseline (per-VS) | batched Business Needs |
|---|---:|---:|
| LLM calls | 25 | **20** |
| cost — average | $0.093 | **$0.073** |
| cost — 24k worst case | $0.211 | **$0.168** |

Business Needs goes from 10 calls to 5 (chunked): **5 fewer calls**, **−21% cost average**, **−20% at
24k**.

---

## Verdict

| change | calls saved | cost saved (avg / 24k) | quality |
|---|---|---|---|
| **merged Capabilities** | 9 | 12% / 26% | small, acceptable trade |
| **batched Business Needs** | 5 | 21% / 20% | **materially worse** (shorter, less-grounded docs) |

**Adopt merged Capabilities** — it's the bigger call-count saving, the cost drop grows on large idea
cards, and the quality trade is small (and nothing is hallucinated). **Keep Business Needs per-VS** —
the saving is real, but it comes by making a prescriptive, architect-facing artifact ~40% shorter and
notably less grounded, which is a bad trade.
