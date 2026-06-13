# How good is our “similar past tickets” search?

*A plain-language report. We tested the search on **373 real tickets**. For each one, the system pulls
the most similar past tickets and shows them to the model as examples ("here's what was done before").
This checks whether those examples are actually any good.*

**How we judge an example.** A pulled past ticket counts as a *match* if it carries one of the same
**Value Streams** the current ticket should have. We also had an **AI reviewer** read each pulled
ticket and say whether it's *genuinely about the same kind of work* — a second opinion that catches
matches that look right on paper but aren't.

---

## Bottom line

- The search is **great at finding** the right examples — the correct Value Stream shows up for **90%**
  of tickets, usually as the **very first** result.
- But **about half** of what it calls a "match" only matches **by coincidence** — two independent
  checks (ignoring generic tags, and an AI reviewer) both say real relevance is **~33–37%**, not the
  **67%** a simple count suggests.
- The cause: **6 generic catch-all tags** + a tail of **"overloaded" tickets** tagged with up to **19**
  Value Streams that match almost anything.
- **Showing 6 past tickets is the sweet spot** — more dilutes the examples without really helping.
- **Worth fixing:** down-weight the generic tags and overloaded tickets when ranking — it sharpens
  relevance *and* helps cover the hard multi-stream tickets.

*Context:* **52%** of tickets belong to a single Value Stream (easy — one answer to find); **48%**
belong to two or more, a few to as many as **19** (hard).

---

## 1. It finds the right examples

For 90% of tickets the correct Value Stream is among the 6 pulled examples, 96% have at least one
genuinely useful example, and for **288 of 373** tickets the *first* result is already a hit. Finding
good examples is not the problem.

![Coverage scorecard](retrieval_charts/coverage.png)

---

## 2. Not every ticket is equally hard

Half the tickets belong to a single Value Stream (easy — one answer to find); the other half belong to
several, a few to as many as 19 (hard). So the coverage numbers are an **average across easy and hard**
tickets.

![How many Value Streams per ticket](retrieval_charts/gt_dist.png)

---

## 3. Hard tickets: we find most, but rarely all

On hard (multi-stream) tickets the search still surfaces **88%** of the streams on average — almost as
good as the **92%** for easy tickets. But getting *every* stream right happens only **63%** of the time
(vs 92% for easy). In plain terms: on a hard ticket we catch the obvious streams and usually **miss one
or two from the long tail**.

![Easy vs hard coverage](retrieval_charts/easy_hard.png)

---

## 4. But “relevant” is overcounted (the important catch)

If we just count "shares a tag," **67%** of pulled tickets look relevant. That's misleading: removing
the 6 generic tags drops it to **33%**, and an AI reviewer reading the actual text puts it at **37%**.
A simple rule and an AI **independently land in the same place** — real relevance is about half the
headline.

![Precision reality check](retrieval_charts/precision_check.png)

---

## 5. Every example we pulled, sorted

Splitting all **3,729** pulled tickets four ways: only **24%** are real matches (right tag *and* same
work), **39%** are lucky matches (right tag, different work), **8%** are the same work tagged
differently, and **29%** are unrelated. So **6 in 10 "matches" are coincidences**.

![Label vs content breakdown](retrieval_charts/crosstab.png)

---

## 6. Why the lucky matches happen

Most pulled tickets are specific (a single tag). But a tail of **"overloaded"** tickets carry up to
**19 tags each** — those match almost any query by accident. Combined with the 6 generic catch-all
tags, they create the coincidental matches.

![Tags per pulled ticket](retrieval_charts/density.png)

---

## 7. More examples is *not* better

Showing 6, 8, or 10 past tickets: more finds slightly more right answers but a steady share of the
extras are junk — a near **1-for-1 trade**. **6 is the sweet spot.**

![Coverage vs relevance across K](retrieval_charts/tradeoff.png)

---

## 8. The first useful example is usually right at the top

For **288 of 373** tickets the #1 result is already useful; only **9** tickets found nothing relevant
at all. The ranking puts good examples first — though the underlying scores barely separate good from
bad (0.51 vs 0.48), so we rely on the *ordering*, not the score size.

![Where the first useful example lands](retrieval_charts/first_rank.png)

---

## All the numbers

| Measure (per ticket) | Show 6 | Show 8 | Show 10 |
|---|---|---|---|
| Right answer found (coverage) | 90% | 92% | 94% |
| Found at least one useful | 96% | 97% | 98% |
| Found EVERY stream | 78% | 81% | 85% |
| Looks relevant | 67% | 65% | 63% |
| Really relevant (minus generic tags) | 33% | 31% | 30% |
| Really relevant (AI double-check) | 37% | 34% | 32% |
| First useful at the top (MRR) | 0.85 | 0.85 | 0.85 |

---

## Plain-language glossary

| Term | What it means |
|---|---|
| **Value Stream / tag** | The business category a ticket belongs to — what we predict. |
| **Coverage** | Did the correct Value Stream show up among the pulled examples. |
| **Looks relevant** | An example that shares a tag with the current ticket. |
| **Really relevant** | An example that's *actually about the same kind of work*, not just a shared tag. |
| **Lucky match** | Shares a tag by coincidence (usually a generic tag) but is different work. |
| **Generic / catch-all tag** | A Value Stream on a large share of tickets, so sharing it means little. |
| **Overloaded ticket** | A past ticket tagged with many Value Streams — matches almost anything. |
| **Easy / hard ticket** | Easy = 1 correct Value Stream; hard = 2 or more. |
