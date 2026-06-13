# How much of the answer does our “similar past tickets” search find?

*A plain-language report. We tested the search on **373 real tickets**. For each one, the system pulls
the most similar past tickets and shows them to the model as examples. This measures **coverage**: of a
ticket's correct **Value Streams**, how many does the search actually surface.*

> **"@6"** means *"when we show the top 6 pulled past tickets."*

---

## Bottom line

- The search **reliably finds the right Value Streams** — the correct ones show up for **90%** of a
  typical ticket's streams, and **96%** of tickets find at least one.
- **78% of tickets find EVERY** correct Value Stream; **18%** find some but miss a few; only **4%** find
  none.
- On average, a ticket has **3.2** correct Value Streams and the search finds **~2.9 of them** (90%).
- The misses are concentrated in the **hard tickets** (those with several Value Streams) — there we find
  *most* streams (88%) but the *complete* set only **63%** of the time.
- **Showing 6 past tickets is enough** — going to 10 adds only ~4 points of coverage.
- **Bottom line:** the search puts the right answers in front of the model — **coverage is not the
  bottleneck.**

---

## 1. What happened to each ticket

When we show the 6 most similar past tickets, every ticket lands in exactly one of three groups (so they
add up to 100%):

![What happened to each ticket](retrieval_charts/coverage.png)

**How to read it.** Each ticket has one or more correct Value Streams to find. Did the 6 examples contain
them?

- **Found ALL — 78%:** every correct Value Stream was in the examples. Nothing missed. ✅
- **Found SOME — 18%:** found at least one, but missed a few. Usually the multi-stream tickets (chart 3).
- **Found NONE — 4%:** none of the correct streams showed up — the only real misses.

So **96% of tickets find at least something** (green + amber) and **78% find everything**.

> *One more number, measured differently:* averaged across tickets, a typical ticket has **90%** of its
> correct streams present in the examples — in plain counts, **~2.9 of its 3.2** correct Value Streams are
> found on average. (That 90% is a per-ticket *average*, not a count of tickets — a ticket that finds 3 of
> its 4 streams contributes 75% to it. Both numbers say the same thing: coverage is strong.)

---

## 2. Not every ticket is equally hard

![How many Value Streams per ticket](retrieval_charts/gt_dist.png)

**How to read it.** Each bar is *how many of the 373 tickets* have that many correct Value Streams:

- **Just 1 — 193 tickets (52%):** one right answer to find. Easy.
- **2–4 — 98**, **5–9 — 54**, **10+ — 28:** the more streams a ticket has, the harder it is to find them
  *all*. The 28 tickets with 10+ streams (a few have 19) are the truly hard cases.

So "90% coverage" is blended across these — the 52% single-stream tickets are easy and lift the average.

---

## 3. Hard tickets: we find most, but rarely all

![Easy vs hard coverage](retrieval_charts/easy_hard.png)

**How to read it.** Two ticket groups (**easy** = 1 stream, 193 tickets; **hard** = 2+, 180 tickets),
each measured two ways:

- **Blue — "Found MOST streams (avg)":** the average fraction of a ticket's streams that were found.
  Easy 92%, hard **88%** — nearly the same, so we find *most* of the answer even on hard tickets.
- **Green — "Found EVERY stream":** how often *all* streams were found. Easy 92%, hard only **63%**.

In plain counts:

- **Easy ticket:** has **1** correct Value Stream → found 92% of the time (≈ **178 of 193** easy tickets
  get their one stream). With a single stream, "found most" and "found every" are the same — that's why
  the two bars match.
- **Hard ticket:** has **~5.6** correct Value Streams on average → the search finds **~4.9 of them**
  (88%), but lands the *complete* set only 63% of the time (≈ **113 of 180** hard tickets).

So the hard-ticket gap (88% vs 63%) is the story: on a ~5.6-stream ticket we usually catch ~4.9 of them
but **miss one or two from the long tail**, so we rarely get *all* of them.

---

## 4. Showing more tickets barely helps

![Coverage across K](retrieval_charts/tradeoff.png)

**How to read it.** The x-axis is *how many past tickets we show* (6, 8, 10):

- **Green — Avg coverage:** climbs only 90% → 94% across the three (≈ **2.9 → 3.0 of 3.2** streams found
  per ticket).
- **Blue — Found everything:** the share of tickets that get *all* their streams climbs only 78% → 85%
  (≈ **291 → 317 of 373** tickets).

Each extra ticket adds a little coverage, but with **diminishing returns** — going from 6 to 10 examples
finds only ~0.1 more stream on a typical ticket. **6 examples is enough** — more adds length without
much benefit.

---

## 5. The right answer is usually at the very top

![Where the first correct stream appears](retrieval_charts/first_rank.png)

**How to read it.** For each ticket, the position of the *first* pulled ticket that carries a correct
Value Stream:

- **Position 1 — 288 of 373 tickets (77%):** the very first result already carries a correct stream.
- **Positions 2, 3, 4–10 — ~76 tickets total:** a few need to look a little deeper.
- **None — 9 tickets (2%):** found nothing correct at all (the only true misses).

So the search not only *finds* the right streams, it usually *ranks them first* — for 3 in 4 tickets the
top example is already on target.

---

## All the numbers

| Measure (per ticket) | Show 6 | Show 8 | Show 10 |
|---|---|---|---|
| Avg coverage (fraction of streams found) | 90% | 92% | 94% |
| Found at least one correct stream | 96% | 97% | 98% |
| Found EVERY correct stream | 78% | 81% | 85% |

---

## Plain-language glossary

| Term | What it means |
|---|---|
| **Value Stream** | The business category a ticket belongs to — what we predict. |
| **Coverage** | Of a ticket's correct Value Streams, how many showed up in the pulled examples. |
| **Found everything** | All of a ticket's correct Value Streams were found — none missed. |
| **Easy / hard ticket** | Easy = 1 correct Value Stream; hard = 2 or more. |
| **@6 / @8 / @10** | When showing the top 6 / 8 / 10 pulled past tickets. |
