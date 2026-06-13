# Choosing the attachment cap and token budget (optimization)

*We want to feed the model the raw ticket text (description + attachments) without it getting too big.
Two knobs control the size: **how many attachments we keep** and **the token budget** (where we cut).
This finds the best combination, measured on **374 tickets**.*

> **"Fits"** = the ticket's text (description + the kept attachments) is under the budget, so nothing
> gets cut. **"Content kept"** = of all a ticket's attachment text, how much survives the attachment cap.

---

## Bottom line

- **The token budget is the real lever; the attachment cap barely matters for coverage.** Because 90% of
  tickets are small to begin with, capping attachments hardly changes how many tickets fit.
- **Keeping 3–4 attachments retains ~all the content** (97–99%). The 5th-plus attachment adds under 3%,
  so dropping the tail is essentially free.
- **The decision simplifies to:** keep **4 attachments** (retains 99% of content, trims only the extreme
  outliers), then pick the **token budget by how many tickets you want to fit**:
  - **16k → 86% fit** (lean / fastest)
  - **24k → 95% fit** (balanced — recommended)
  - **32k → 98% fit** (most generous)
- The few tickets that still exceed the budget are the genuinely huge ones (big slide decks); they get
  gracefully truncated, not the whole corpus.

---

## 1. The token budget drives coverage — not the attachment cap

![Coverage vs budget](token_charts/coverage_curves.png)

**How to read it.** Each line is one attachment cap (keep 1 / 3 / 4 / all). The x-axis is the token
budget; the y-axis is the % of tickets whose text fits under it.

- **All the lines rise steeply with budget** — going from 8k to 24k lifts coverage from ~68% to ~95%.
  The budget is what moves the needle.
- **The lines sit close together** (cap-4 and cap-all almost overlap) — so capping attachments hardly
  changes coverage. Most tickets have ≤4 attachments and are small either way; the cap only touches the
  ~10% with 5+.
- **The "keep 1" line is highest** only because it throws away the most content (see chart 2) — cheap
  coverage at a real cost.

---

## 2. Keeping 3–4 attachments retains almost all the content

![Content kept by cap](token_charts/content_kept.png)

**How to read it.** Each bar is how much of a ticket's attachment text survives that cap:

- **Keep 1 — 77%:** drops a quarter of the content. Too aggressive.
- **Keep 3 — 97%**, **Keep 4 — 99%:** retains essentially everything. The knee is here.
- **Keep 5 / all — 100%:** the 5th-plus attachment adds under 3% — not worth the extra tokens.

So **cap at 4** (or 3) keeps virtually all the content while letting us drop the big, low-value tail.

---

## 3. The recommended operating points

With the cap fixed at **4 attachments** (99% content kept), the budget sets coverage:

| Budget | Tickets that fit | Tickets truncated | Best for |
|---|---|---|---|
| 12k | 78% | 22% | very tight latency |
| **16k** | 86% | 14% | lean / fast |
| **24k** | **95%** | 5% | **balanced (recommended)** |
| 32k | 98% | 2% | most generous |

**Recommendation: keep 4 attachments + a 24k-token budget.** It fits 95% of tickets untouched, keeps
99% of their content, and the 5% that exceed it are the genuinely huge slide-deck tickets — those get
truncated at the budget rather than dropping a whole attachment.

If latency is the priority, **16k** is the lean alternative (86% fit). If completeness matters more,
**32k** (98% fit). The cap stays at 4 in every case.

---

## How this maps to the current setup

- The current condense step uses a **40k-character** budget (≈ 10k tokens) and **top-4** attachments.
  The top-4 choice is already right (this analysis confirms it). The budget, in tokens, is what we're
  re-deciding — and ~10k tokens currently fits only ~70–75% of tickets, so a move to ~24k tokens would
  fit far more raw text untouched.
- **The same budget should apply to the historical tickets** shown as precedent during prediction, so a
  giant past ticket can't blow up the prompt.

---

## The full grid (for reference)

% of tickets that fit, for every (attachment cap × token budget) pair:

| keep \ budget | 4k | 6k | 8k | 12k | 16k | 24k | 32k |
|---|---|---|---|---|---|---|---|
| 1 | 63% | 74% | 81% | 88% | 95% | 98% | 99% |
| 2 | 53% | 65% | 74% | 83% | 91% | 97% | 98% |
| 3 | 51% | 62% | 70% | 80% | 88% | 95% | 98% |
| **4** | 51% | 61% | 68% | 78% | **86%** | **95%** | 98% |
| 5 | 51% | 61% | 68% | 78% | 86% | 94% | 98% |
| all | 51% | 61% | 68% | 78% | 86% | 94% | 97% |

Capped token sizes (description + largest N attachments): median ~3.9k, p90 ~18k, p95 ~24.5k, max ~88k
(the max is the one huge deck — the outlier the budget exists to bound).
