# Value Stream prediction — representation EDA

**Question:** for VS prediction, what text representation works best in each of the three places
text is used — and can we drop summarization to save cost?

**Setup (held constant across every run):**
- 100 tickets with **≥3 ground-truth VS** (`--min-gt 3 --sample 100`, fixed seed) — the hard,
  discriminating cases; single-VS tickets wash out differences.
- `--count-mode gt` — request exactly the GT count, so micro **F1 = P = R** (one clean number per
  run) and no count-generosity bias.
- evidence mode, the Recall selection prompt, K=6 historic neighbours, judge on.

## The three places text is used
| place | what it does | knob |
|---|---|---|
| **Retrieval** | finds the 6 similar past tickets (embedded + searched) | summary vs raw@7k index |
| **New-ticket prompt** | the ticket context the LLM reads to pick VS | `--raw-text` (summary vs raw) |
| **Historic block** | how each of the 6 neighbours is shown in the prompt | `--historic-repr` (summary/raw/description/snippet) |

These are independent. The ladder below varies one at a time.

## Results

![F1 by representation](vs_repr_charts/f1_ladder.png)

| run | prompt | historic | retrieval | **F1** | exact-set | avg latency |
|---|---|---|---|---|---|---|
| all-summary | summary | summary | summary | 0.715 | 23% | 4.2s |
| **raw + summary** | **raw** | **summary** | **summary** | **0.786** | **36%** | 5.8s |
| raw + raw@1500 | raw | raw@1500 | summary | 0.781 | 26% | 5.6s |
| raw + raw@3000 | raw | raw@3000 | summary | 0.768 | 24% | 6.3s |
| raw + description | raw | description | summary | 0.780 | 31% | 4.4s |
| raw + raw@7k | raw | raw@7k | summary | 0.780 | 30% | 9.4s |
| raw@7k INDEX | raw | raw@7k | **raw@7k** | 0.754* | 23% | 13.9s |

*raw@7k-index on 98 tickets (2 lost to an Azure Search timeout, scored as misses → ~1–2pts low).

**How to read it:** the big step is summary→raw on the **new-ticket prompt** (0.715 → 0.786). After
that, swapping the **historic block** representation barely moves F1 (0.768–0.786) — and the last
bar (raw@7k *retrieval*) drops *below* the pack. So the prompt is the lever, the historic block is a
wash, and raw retrieval is a regression.

## Finding 1 — the lever is the NEW-TICKET prompt
Feeding the new ticket's **raw text** instead of its summary is **+0.071 F1 (0.715 → 0.786)** and
nearly doubles exact-set (23% → 36%). Retrieval is already perfect at surfacing candidates (every GT
reaches the LLM), so all of this gain is the LLM *choosing* better when it sees the full ticket.

## Finding 2 — the historic block representation is a wash (so use the cheapest)
Among the raw-prompt runs the historic block spans only 0.768–0.786: summary (0.786) ≈ description
(0.780) ≈ raw@1500 (0.781) ≈ raw@7k (0.780), with raw@3000 slightly *worse* (0.768). More raw
precedent does **not** help — it dilutes. **Summary historic is marginally best and the cheapest.**

## Finding 3 — summary retrieval beats raw@7k retrieval (the cost question)

![Retrieval comparison](vs_repr_charts/retrieval_compare.png)

To test dropping summarization entirely, we re-embedded the index on **raw@7k** (no summary) and
retrieved with raw. The decider is **historic-lane recall** — did the precedent search surface the
GT (in evidence mode the 50-VS candidate pool makes review-pool recall structurally 1.0, so *that*
isn't the signal — the historic lane is).

- summary retrieval: historic-lane R **0.902** → F1 **0.786**
- raw@7k retrieval: historic-lane R **0.843** → F1 **0.754**

**How to read it:** the ~460-token summary embeds the *whole* ticket cleanly; raw@7k keeps only ~half
of a big ticket, so it retrieves **worse neighbours**. Since precedent drives recall (GT *backed* by
historic is picked ~0.82, *not-backed* only ~0.38), worse precedent → lower recall → ~3 F1 points
lost. **Dropping the summary costs quality.**

## Latency / cost

![Latency by representation](vs_repr_charts/latency.png)

**How to read it:** latency tracks the LLM **prompt size**. summary historic ≈ 6×460 tokens; raw@7k
historic ≈ 6×7k = 42k tokens, which blows the prompt to ~55k tokens and spikes prediction to 132s on
big-neighbour tickets. This is a *second* cost axis, independent of the summary question: even if you
keep summaries, **never ship raw@7k historic** — it's ~4–5× the runtime token cost for zero quality.

## Verdict
**Locked config: summary retrieval + raw new-ticket prompt + summary historic — F1 0.786.**

- The summary you "can't eliminate" turns out to be the thing buying your best retrieval.
- Dropping summarization (raw@7k retrieval) is **worse on every quality axis and 2.4× slower** — not
  a marginal trade, a regression. The summary-free idea is dead.
- The new-ticket **raw** prompt is the real win (+0.07); keep it.
- Use the **cheapest** historic block (summary) — raw/description add cost for nothing.
