# Historic-lane retrieval evaluation — findings

**Run:** 373 IDMT tickets (all with ≥1 GT Value Stream), K = 6 / 8 / 10, one retrieval per ticket
sliced at each K. **Relevance:** a retrieved past ticket is *label-relevant* when its Value Stream
labels overlap the query ticket's GT Value Streams (free, automatic). A separate **LLM content
judge** rated each retrieved ticket for *topical* similarity (same kind of change), independent of
labels — the diagnostic that tells real precedent from coincidental label overlap.

---

## Headline

**The retriever's *coverage* is genuinely strong, but its *precision* is roughly half what the
label metric reports — inflated by a handful of broad Value Streams and a tail of many-label
tickets.** Two independent checks agree on this, which is what makes it trustworthy.

- **Coverage is excellent.** At K=6 the retrieved tickets already contain **90.2%** of the correct
  Value Streams (recall@6), **96.0%** of queries have at least one relevant ticket (hit@6), and the
  first relevant ticket is at **rank 1 for 288 of 373 queries** (MRR 0.846). 78% of queries have
  *all* their GT covered by precedent at K=6 (85% at K=10).
- **But label-precision overcounts badly.** Raw precision@6 is **67%**, yet:
  - removing the 6 broad Value Streams drops it to **33%** (precision_strict), and
  - the independent LLM content judge puts it at **37%** (content-precision).
  Two unrelated methods — a rule (exclude broad VS) and an LLM (topical judgement) — **independently
  land at ~33–37%**, vs the 67% headline. About **half** of "relevant" retrieved tickets share a
  Value Stream by coincidence, not because they're genuine precedent.
- **The mechanism:** 6 broad streams + a tail of *aggregator tickets* carrying up to **19 VS labels
  each** (92 retrieved instances had 19 labels). A ticket tagged with 19 streams overlaps almost any
  query by chance — a lucky-match machine.
- **K = 6 is confirmed the sweet spot.** Going up in K trades recall for precision ~1:1
  (6→8: +2.3% recall, −2.5% precision; 8→10: +2.0% recall, −1.6% precision), and both strict- and
  content-precision keep falling. The earlier "keep K=6" decision is now measured directly.

---

## Metrics by K

| metric | K=6 | K=8 | K=10 |
|---|---|---|---|
| **Recall@k** (GT coverage) | 90.2% | 92.5% | 94.4% |
| **Precision@k** (label) | 67.2% | 64.7% | 63.1% |
| **Precision@k (strict, excl. broad VS)** | 33.3% | 31.4% | 30.1% |
| **Content-precision@k** (LLM judge) | 36.5% | 33.7% | 32.3% |
| **Hit@k** | 96.0% | 96.8% | 97.6% |
| **MRR** | 0.846 | 0.848 | 0.848 |
| **nDCG@k** | 0.861 | 0.859 | 0.858 |
| **Fully-covered queries** | 78.0% | 81.2% | 85.0% |
| **Zero-relevant queries** (total miss) | 4.0% | 3.2% | 2.4% |
| **Mean relevant tickets in top-K** | 4.03 | 5.17 | 6.31 |
| **Evidence density** (VS/ticket, mean) | 3.48 | 3.52 | 3.55 |

**Marginal effect of adding tickets:**

| step | recall gained | precision change |
|---|---|---|
| 6 → 8 | +2.3% | −2.5% |
| 8 → 10 | +2.0% | −1.6% |

---

## Are the matches real? — label vs content (3,729 retrieved tickets judged)

| | count | share |
|---|---|---|
| **label + content** (real hit) | 914 | 24.5% |
| **label, NOT content** (lucky label match) | 1,438 | 38.6% |
| **content, NOT label** (similar but different label) | 292 | 7.8% |
| **neither** | 1,085 | 29.1% |

- Of all **label-relevant** tickets (2,352), only **38.9%** were judged genuinely similar — **61% are
  lucky matches**. This is the core caveat of using VS-overlap as relevance.
- The **content-NOT-label** band (7.8%) is the *opposite* failure: genuinely similar tickets tagged
  with a different (often sibling) Value Stream — a taxonomy/labelling gap, not a retrieval miss.

---

## Ranking quality and the score signal

- **MRR 0.846 / first-relevant rank-1 for 288/373 queries** → the top result is usually relevant; the
  ranker puts useful precedent first.
- **But the raw score barely separates relevant from irrelevant:** mean score 0.510 (relevant) vs
  0.480 (irrelevant) — only a 0.03 gap. So the retriever *ranks* well at the very top, but the score
  *magnitude* is a weak relevance signal — consistent with the earlier finding that semantic scores
  are too weak to trust as a candidate hint (why we dropped them from the prompt).

---

## Coverage and the corpus shape

- **Zero-relevant (total retrieval misses):** only **9 of 373 tickets** had no relevant ticket at any
  rank. Coverage is rarely the failure.
- **Evidence density is bimodal:** median **1 VS/ticket** (most retrieved tickets are specific) but a
  long tail — 92 retrieved instances carry **19 VS each**. Those aggregator tickets drive the lucky
  matches.
- **GT size:** mean 3.2 VS/ticket, median 1, max 19 — half the tickets have a single correct VS, but
  some span many.

---

## Concrete examples

**Lucky label match (share a broad VS, not the same change):**
`IDMT-10056` (GT: VSR00074591) retrieved `IDMT-30124`, which carries **8** Value Streams
(VSR00074584, …590, …591, …595, …601, …609, …610, VS00168129) — three of them broad. It shares
VSR00074591 by virtue of being a multi-stream aggregator; the content judge rated it **not** a
genuine precedent. Classic lucky match.

**Sibling tickets that share a label but aren't precedent:**
`IDMT-10073` ↔ `IDMT-10075` ↔ `IDMT-10076` all carry VSR00074595 and retrieve each other at rank 1
(scores ~0.62–0.66), yet all are judged content-irrelevant — same label, different work.

**Content-relevant but different label (taxonomy gap):**
`IDMT-10073` (GT VSR00074**595**) retrieved `IDMT-34338` (VSR00074**594**) — adjacent/sibling Value
Streams; the judge calls it topically relevant though the labels don't match.

**Total miss:** `IDMT-17825, 18853, 25106, 31030, 31225` — no relevant ticket retrieved at all.

---

## What this means for the system

1. **For the generation step's ceiling, retrieval is doing its job.** Recall@6 = 90% (this is the
   `historic_lane` coverage the prompt relies on); the right precedent is almost always present, near
   the top. The model then uses ~79% of it (the generation eval's "precedent backed").
2. **The model is filtering heavily — and has to.** Of ~10 shown tickets, only ~3–4 are genuine
   precedent; the rest are broad/coincidental label matches. That the generation eval still works
   means the model + the ticket content do the filtering. **Reducing the lucky matches in retrieval**
   (down-weighting the 6 broad streams and the 19-VS aggregator tickets) is the clearest lever to
   sharpen the precedent without losing coverage.
3. **K = 6 stands.** Higher K buys little coverage for a steady precision cost.

## Caveats

- **VS-label relevance is the primary metric** (it's the end-task signal and it's what the prompt
  consumes); content-relevance is the **diagnostic**, and the LLM judge can be strict — read the
  61% "lucky" figure as "needs review," corroborated by the rule-based 33% strict-precision rather
  than as exact truth. The agreement of the two methods is the trustworthy part.
- The content judge read each ticket's businessSummary; very terse tickets give it less to go on.
