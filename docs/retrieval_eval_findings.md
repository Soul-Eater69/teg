# How good is our "similar past tickets" search?

*A plain-language report. We tested the search on **373 real tickets**. For each one, the system
pulls the most similar past tickets and shows them to the model as examples ("here's what was done
before"). This checks whether those examples are actually any good.*

How we decide an example is **useful**: a past ticket counts as a match if it was tagged with one of
the **same Value Streams** the current ticket should have. We also had an **AI reviewer** read each
pulled ticket and say whether it's *genuinely about the same kind of work* — a second opinion that
catches matches that look right on paper but aren't.

---

## The 30-second version

```
THE GOOD — the right examples almost always show up
  Right Value Stream was found        ██████████████████░░  90%
  Found at least one useful example   ███████████████████░  96%
  Best example sits at the very top   ███████████████░░░░░  77% of tickets

THE CATCH — but many "matches" aren't really relevant
  Looks relevant (shares a tag)       █████████████░░░░░░░  67%
  Actually relevant (broad tags out)  ███████░░░░░░░░░░░░░  33%
  Actually relevant (AI double-check) ███████░░░░░░░░░░░░░  37%
```

**In one line:** the search is **great at finding** the right examples, but **about half of what it
labels "relevant" only matches by coincidence** — and two completely separate checks agree on that.

*Context for the numbers:* **52% of tickets** belong to a single Value Stream (easy — one answer to
find); **48%** belong to two or more, a few to as many as **19** (hard). The headline coverage is an
average across both — see Finding 1b.

---

## Finding 1 — It finds the right examples (this part is strong)

For 90% of tickets, the correct Value Stream showed up somewhere in the top 6 past tickets. For 96%,
at least one genuinely useful example was found. And the best example is usually the *very first*
result — for 288 of 373 tickets, the #1 result was already a hit.

```
Where does the first useful example land in the list?
  Position #1   ██████████████████████████████  288 tickets
  Position #2   ███▌                              36
  Position #3   ██                                20
  #4 or lower   ██                                20
  Never found   █                                  9
```

> **Takeaway:** the system rarely *fails to find* good examples. Finding isn't the problem.

---

## Finding 1b — Not every ticket is equally hard (read the 90% with this in mind)

Half the tickets are **easy** — they belong to a single Value Stream, so "find the one right answer"
is all it takes. The other half belong to **several**, and a handful belong to *many* (5 tickets are
tagged with **19** Value Streams each). Covering *all* of those is far harder.

```
How many Value Streams does a ticket actually have?  (373 tickets)
  Just 1            ███████████████████████  193  (52%)  ← easy: one answer to find
  2–4              ████████████              98   (26%)
  5–9              ██████                    54   (14%)
  10 or more       ███                       28    (8%)  ← hard: covering all is tough
```

Here's the honest split (at K=6, showing 6 past tickets):

| Ticket type | Found *most* of its streams (avg coverage) | Found *every* stream (fully covered) |
|---|---|---|
| **Easy** (1 Value Stream) | 92% | 92% |
| **Hard** (2 or more) | 88% | **63%** |
| All tickets | 90% | 78% |

Two takeaways from this:

- **On average, the search does almost as well on hard tickets as easy ones** — it surfaces 88% of a
  hard ticket's streams vs 92% for an easy one. It's good at finding *most* of the answer even when
  there's a lot to find.
- **But getting *everything* right is much harder on multi-stream tickets** — we find *all* the
  streams only **63%** of the time (vs 92% for single-stream). In plain terms: on a hard ticket we
  usually catch the obvious streams and **miss a stream or two from the long tail**.

(For single-stream tickets, "found most" and "found all" are the same thing — there's only one to
find — which is why both are 92%.)

> **One thing to notice:** those 10-plus-stream tickets are a *double problem* — they're the hardest
> to fully cover, **and** (from Finding 3) they're the "overloaded" tickets that cause the lucky
> matches. Fixing how the system treats them helps both coverage *and* relevance.

---

## Finding 2 — But "relevant" is overcounted (the important catch)

If we just count "shares a tag," **67%** of the pulled tickets look relevant. That number is
misleading. Two independent checks cut it roughly in half:

```
Of the tickets we pull, how many are REALLY relevant?
  Counting any shared tag         █████████████░░░░░░░  67%   ← the flattering number
  Ignoring generic catch-all tags ███████░░░░░░░░░░░░░  33%
  AI reviewer's honest opinion    ███████░░░░░░░░░░░░░  37%
```

The striking part: a **simple rule** (ignore the generic tags) and an **AI reading the actual text**
arrive at almost the same answer — ~33% vs ~37%. When two unrelated methods agree, you can trust it.

**Breaking down every example we pulled (3,729 of them):**

```
  Real match (right tag AND same work)   █████░░░░░░░░░░░░░░░░  24%   ✅ genuine
  Lucky match (right tag, different work) ████████░░░░░░░░░░░░  39%   ⚠️ coincidence
  Same work but tagged differently        █▌░░░░░░░░░░░░░░░░░░   8%   (a labeling gap)
  Unrelated                               ██████░░░░░░░░░░░░░░  29%
```

So of everything that "shares a tag," **6 in 10 are lucky coincidences**, not real precedent.

---

## Finding 3 — Why the lucky matches happen

Two culprits, both easy to picture:

**1. Generic "catch-all" Value Streams.** Six Value Streams are so broad they're attached to a huge
share of tickets. Sharing one of *those* tells you almost nothing — like saying two emails are
related because both mention "the company."

**2. Overloaded tickets.** Some past tickets are tagged with a *pile* of Value Streams — a handful
carry **19 tags each**. A ticket tagged with 19 things will "match" almost any query by accident.

```
How many tags does a pulled ticket carry?
  1 tag    ██████████████████████████████  1885   ← most are specific (good)
  2–5 tags ████████████████                1047
  6–10     ████████                         496
  11–18    ████                             210
  19 tags  █▌                                92    ← the "matches everything" tickets
```

Most tickets are specific (1 tag), but that tail of 19-tag tickets quietly drives the false matches.

---

## Finding 4 — More examples is *not* better

We tried showing 6, 8, and 10 past tickets. Showing more finds slightly more right answers, but at a
steady cost: more of the extras are junk. It's a near 1-for-1 trade.

| Showing… | Right answer found | Looks relevant | Really relevant (AI) | First useful at top |
|---|---|---|---|---|
| **6 tickets** | 90% | 67% | 37% | 0.85 |
| 8 tickets | 92% | 65% | 34% | 0.85 |
| 10 tickets | 94% | 63% | 32% | 0.85 |

```
Going from 6 → 8 → 10 examples:
  Coverage gained   ▲ +2%   then ▲ +2%   (small)
  Relevance lost    ▼ −2%   then ▼ −2%   (steady)
```

> **Takeaway:** **6 is the sweet spot.** Adding more dilutes the examples without really helping.

---

## What this means (and the one thing worth fixing)

1. **For "did the right example show up?" — the search is doing its job.** The right precedent is
   almost always present and near the top. This is what the model leans on, and it works.
2. **The model has to do a lot of filtering.** Out of ~10 examples shown, only ~3–4 are genuinely on
   point; the rest share a generic tag. The model copes (it still picks well), but it's wading
   through noise.
3. **The clear improvement:** stop the lucky matches at the source — **down-weight the 6 generic
   Value Streams and the "19-tag" overloaded tickets** when ranking past tickets. That sharpens the
   examples without losing the coverage we're happy with.
4. **Keep showing 6 examples.** More isn't better.

A small honest note: the AI reviewer can be a strict grader, so read "6 in 10 are lucky" as
"roughly half — needs a look," trusted because the simple generic-tag rule landed in the same place.

---

## Mini-glossary (plain terms used above)

| Term in the report | What it means |
|---|---|
| **Value Stream / tag** | The business category a ticket belongs to — the thing we predict. |
| **Right answer found** | The correct Value Stream appeared somewhere in the pulled examples. |
| **Looks relevant** | An example that shares a tag with the current ticket. |
| **Really relevant** | An example that's *actually about the same kind of work* (not just a shared tag). |
| **Lucky match** | Shares a tag by coincidence — usually a generic tag — but is different work. |
| **Generic / catch-all tag** | A Value Stream attached to a large share of tickets, so sharing it means little. |
| **Overloaded ticket** | A past ticket tagged with many Value Streams, so it matches almost anything. |
| **First useful at top** | How often the best example is the #1 result (higher = better). |
