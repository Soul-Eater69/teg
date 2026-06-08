# Value Stream Candidate Merger

This document explains `src/teg/value_stream/candidate_merger.py` at code level.
The merger takes two retrieval lanes, combines their evidence by value-stream ID,
then builds a bounded review pool for the LLM selection step.

It does not decide the final value streams. It only prepares a ranked candidate
set that is small enough, and evidence-rich enough, for review.

## Inputs

The merger receives two lists:

```python
value_stream_hits: list[ValueStreamHit]
historical_hits: list[HistoricalHit]
```

`value_stream_hits` are semantic catalogue matches. Each hit points directly to
an approved value stream and has a semantic score.

`historical_hits` are similar historical tickets. Each historical ticket can have
one or more value-stream labels attached to it. Those labels become historical
support for candidate value streams.

## Output

The main internal output is:

```python
list[ValueStreamCandidate]
```

Each `ValueStreamCandidate` represents one possible value stream, with semantic
evidence, historical evidence, or both.

The final review pool is also a `list[ValueStreamCandidate]`, but filtered,
ranked, and capped by `CandidateMergePolicy`.

## Important Types

### `CandidateMergePolicy`

`CandidateMergePolicy` contains the tuning knobs for review-pool construction.

```python
@dataclass(frozen=True)
class CandidateMergePolicy:
    window: int = 18
    max_semantic_plus_historic: int = 18
    max_historic_only: int = 6
    max_semantic_only: int = 3
    historic_min_hits: int = 1
    historic_min_best: float = 0.55
    historic_min_weighted: float = 0.5
    semantic_min_score: float = 1.00
```

What each field controls:

- `window`: total max candidates sent to the LLM.
- `max_semantic_plus_historic`: max candidates from both semantic and historical lanes.
- `max_historic_only`: max candidates that only came from historical tickets.
- `max_semantic_only`: max candidates that only came from semantic catalogue search.
- `historic_min_hits`: minimum number of supporting historical tickets for historic-only candidates.
- `historic_min_best`: minimum best historical hit score for historic-only candidates.
- `historic_min_weighted`: minimum weighted support for historic-only candidates.
- `semantic_min_score`: minimum semantic score for semantic-only candidates.

The default lane priority is:

1. `semantic_plus_historic`
2. `historic_only`
3. `semantic_only`

### `ValueStreamCandidate`

`ValueStreamCandidate` is the merged internal record.

Identity fields:

```python
value_stream_id: str
value_stream_name: str
value_stream_description: str = ""
```

Semantic-lane fields:

```python
from_semantic: bool = False
semantic_score: float = 0.0
semantic_rank: int | None = None
```

Historical-lane fields:

```python
from_historical: bool = False
supporting_ticket_count: int = 0
direct_count: int = 0
implied_count: int = 0
best_support_score: float = 0.0
avg_support_score: float = 0.0
weighted_support: float = 0.0
source_ticket_ids: list[str] = field(default_factory=list)
evidence: list[str] = field(default_factory=list)
```

Bucket field:

```python
lane: Bucket = "semantic_only"
```

The `lane` is assigned after both retrieval sources have been merged.

## Function Breakdown

## `build_candidates`

```python
def build_candidates(
    value_stream_hits: list[ValueStreamHit],
    historical_hits: list[HistoricalHit],
    *,
    max_supporting_tickets: int = _MAX_SUPPORTING_TICKETS,
) -> list[ValueStreamCandidate]:
```

This function creates a single candidate per value-stream ID by merging semantic
catalogue hits and historical-ticket support.

### Step 1: Create a lookup table

```python
by_id: dict[str, ValueStreamCandidate] = {}
```

The function stores candidates by `value_stream_id`. This is what lets semantic
and historical evidence merge into the same candidate instead of creating
duplicates.

### Step 2: Add semantic catalogue hits

```python
for rank, hit in enumerate(value_stream_hits, start=1):
```

For each semantic hit:

1. Skip it if `hit.value_stream_id` is empty.
2. Create a candidate if this value stream has not appeared yet.
3. Mark the candidate as semantic-backed.
4. Store the semantic score.
5. Store the semantic rank.

Code path:

```python
if not hit.value_stream_id:
    continue

candidate = by_id.setdefault(
    hit.value_stream_id,
    ValueStreamCandidate(
        value_stream_id=hit.value_stream_id,
        value_stream_name=hit.value_stream_name,
        value_stream_description=hit.value_stream_description,
    ),
)
candidate.from_semantic = True
candidate.semantic_score = hit.score
candidate.semantic_rank = rank
```

After this step, every semantic hit has a candidate keyed by value-stream ID.

### Step 3: Group historical evidence by value stream

```python
for vs_id, pairs in _group_historical_by_vs(historical_hits).items():
```

`_group_historical_by_vs` converts historical ticket hits into groups like:

```python
{
    "VS-100": [(historical_hit_1, label_a), (historical_hit_2, label_b)],
    "VS-200": [(historical_hit_3, label_c)],
}
```

Each pair is:

```python
(HistoricalHit, value_stream_label)
```

### Step 4: Create or update candidates from historical evidence

```python
first_label = pairs[0][1]
candidate = by_id.setdefault(
    vs_id,
    ValueStreamCandidate(
        value_stream_id=vs_id,
        value_stream_name=first_label.value_stream_name,
    ),
)
```

If semantic search already created this candidate, this reuses it.

If the candidate only appears through historical tickets, this creates it from
the first historical label.

### Step 5: Calculate historical support fields

```python
ticket_ids = _unique(hit.ticket_id for hit, _ in pairs if hit.ticket_id)
scores = [hit.score for hit, _ in pairs]
```

The candidate stores unique supporting ticket IDs and the historical hit scores.

Then the function fills historical metrics:

```python
candidate.from_historical = True
candidate.supporting_ticket_count = len(ticket_ids)
candidate.source_ticket_ids = ticket_ids[:max_supporting_tickets]
candidate.direct_count = sum(1 for _, label in pairs if label.support_type == "direct")
candidate.implied_count = sum(1 for _, label in pairs if label.support_type == "implied")
candidate.best_support_score = max(scores, default=0.0)
candidate.avg_support_score = (sum(scores) / len(scores)) if scores else 0.0
```

Meaning:

- `supporting_ticket_count`: number of unique historical tickets supporting this value stream.
- `source_ticket_ids`: first few supporting ticket IDs, capped by `max_supporting_tickets`.
- `direct_count`: how many historical labels are direct support.
- `implied_count`: how many historical labels are implied support.
- `best_support_score`: strongest historical retrieval score.
- `avg_support_score`: average historical retrieval score.

### Step 6: Calculate weighted support

```python
candidate.weighted_support = round(
    _support_weight(candidate.best_support_score) * candidate.supporting_ticket_count, 4
)
```

This turns the best historical score into a coarse multiplier, then multiplies it
by the number of supporting tickets.

The scoring comes from `_support_weight`:

```python
score >= 0.80 -> 1.0
score >= 0.70 -> 0.6
score >= 0.60 -> 0.3
else          -> 0.0
```

Example:

```text
best_support_score = 0.82
supporting_ticket_count = 2
weighted_support = 1.0 * 2 = 2.0
```

### Step 7: Collect evidence text

```python
candidate.evidence = _unique(
    label.evidence or label.reason for _, label in pairs if (label.evidence or label.reason)
)[:max_supporting_tickets]
```

This captures short evidence snippets from historical labels.

It prefers `label.evidence` when available, otherwise uses `label.reason`.

The result is deduped and capped to `max_supporting_tickets`.

### Step 8: Assign lanes

```python
for candidate in by_id.values():
    candidate.lane = _lane(candidate)
```

Every candidate is assigned one of three lanes:

- `semantic_plus_historic`: found in both retrieval lanes.
- `semantic_only`: found only by semantic catalogue search.
- `historic_only`: found only through historical tickets.

Then the function returns all candidates:

```python
return list(by_id.values())
```

## `select_review_pool`

```python
def select_review_pool(
    candidates: list[ValueStreamCandidate],
    *,
    policy: CandidateMergePolicy = CandidateMergePolicy(),
) -> list[ValueStreamCandidate]:
```

This function turns the merged candidate list into the final bounded review pool.

It performs three operations:

1. Split candidates by lane.
2. Gate weak candidates where needed.
3. Sort and fill the pool in priority order.

### Step 1: Rank semantic-plus-historical candidates

```python
semantic_plus = sorted(
    (c for c in candidates if c.lane == "semantic_plus_historic"),
    key=_sort_semantic_plus_historic,
)
```

No gate is applied here. If a candidate appears in both semantic and historical
lanes, it is considered strong enough to review.

Sorting uses `_sort_semantic_plus_historic`.

### Step 2: Gate and rank historic-only candidates

```python
historic_only = sorted(
    (c for c in candidates if c.lane == "historic_only" and _is_good_historic_only(c, policy)),
    key=_sort_historic_only,
)
```

Historic-only candidates must pass `_is_good_historic_only`.

They are sorted by `_sort_historic_only`.

### Step 3: Gate and rank semantic-only candidates

```python
semantic_only = sorted(
    (c for c in candidates if c.lane == "semantic_only" and _is_strong_semantic_only(c, policy)),
    key=_sort_semantic_only,
)
```

Semantic-only candidates must pass `_is_strong_semantic_only`.

They are sorted by `_sort_semantic_only`.

### Step 4: Fill the pool by lane priority

```python
pool: list[ValueStreamCandidate] = []
pool += semantic_plus[: policy.max_semantic_plus_historic]
```

First, add semantic-plus-historical candidates.

Then calculate remaining room:

```python
room = max(0, policy.window - len(pool))
```

Add historic-only candidates:

```python
pool += historic_only[: min(policy.max_historic_only, room)]
```

Recalculate room:

```python
room = max(0, policy.window - len(pool))
```

Add semantic-only candidates:

```python
pool += semantic_only[: min(policy.max_semantic_only, room)]
```

Finally enforce the total window:

```python
return pool[: policy.window]
```

## Helper Functions

## `_group_historical_by_vs`

```python
def _group_historical_by_vs(historical_hits):
```

Loops through every historical hit and every value-stream label on that hit.

If the label has a `value_stream_id`, it appends the `(hit, label)` pair under
that value-stream ID.

This is the main bridge from ticket-level historical matches to value-stream-level
candidate support.

## `_lane`

```python
def _lane(candidate: ValueStreamCandidate) -> Bucket:
```

Assigns the candidate bucket:

```python
if candidate.from_semantic and candidate.from_historical:
    return "semantic_plus_historic"
if candidate.from_semantic:
    return "semantic_only"
return "historic_only"
```

## `_is_good_historic_only`

```python
def _is_good_historic_only(c: ValueStreamCandidate, policy: CandidateMergePolicy) -> bool:
```

Returns `True` when any historical signal is strong enough:

```python
c.supporting_ticket_count >= policy.historic_min_hits
or c.direct_count >= 1
or c.best_support_score >= policy.historic_min_best
or c.weighted_support >= policy.historic_min_weighted
```

With the default policy, one supporting historical ticket is enough because
`historic_min_hits` is `1`.

## `_is_strong_semantic_only`

```python
def _is_strong_semantic_only(c: ValueStreamCandidate, policy: CandidateMergePolicy) -> bool:
```

Returns `True` only when the semantic score meets the configured floor:

```python
return c.semantic_score >= policy.semantic_min_score
```

With defaults, semantic-only candidates need:

```text
semantic_score >= 1.00
```

## `_sort_semantic_plus_historic`

```python
def _sort_semantic_plus_historic(c: ValueStreamCandidate) -> tuple:
```

Sorts candidates that have both semantic and historical support.

It creates a blended score:

```python
boost = min(1.0, c.supporting_ticket_count / 10.0) * 0.20 + c.best_support_score * 0.15
blended = c.semantic_score + boost
```

The first part of `boost` rewards more supporting tickets, up to a max of `0.20`.
The second part rewards the best historical score.

The sort tuple is:

```python
return (
    -blended,
    -c.semantic_score,
    -c.best_support_score,
    -c.weighted_support,
    -c.supporting_ticket_count,
    c.value_stream_name.lower(),
)
```

Negative numbers are used because Python sorts ascending by default. Returning
`-blended` means higher blended scores sort first.

Tie-breakers are:

1. higher semantic score
2. higher best historical score
3. higher weighted support
4. more supporting tickets
5. alphabetical value-stream name

## `_sort_semantic_only`

```python
def _sort_semantic_only(c: ValueStreamCandidate) -> tuple:
```

Sorts semantic-only candidates by semantic score descending, then name ascending.

```python
return (-c.semantic_score, c.value_stream_name.lower())
```

## `_sort_historic_only`

```python
def _sort_historic_only(c: ValueStreamCandidate) -> tuple:
```

Sorts historic-only candidates by historical strength.

```python
return (
    -c.best_support_score,
    -c.weighted_support,
    -c.direct_count,
    -c.supporting_ticket_count,
    -c.implied_count,
    -c.avg_support_score,
    c.value_stream_name.lower(),
)
```

Priority is:

1. higher best support score
2. higher weighted support
3. more direct labels
4. more supporting tickets
5. more implied labels
6. higher average support score
7. alphabetical value-stream name

## `_support_weight`

```python
def _support_weight(score: float) -> float:
```

Converts a best historical score into a coarse weight:

```python
if score >= 0.80:
    return 1.0
if score >= 0.70:
    return 0.6
if score >= 0.60:
    return 0.3
return 0.0
```

This avoids treating every historical score as equally meaningful.

## `_unique`

```python
def _unique(values) -> list[str]:
```

Dedupes values while preserving first-seen order.

It:

1. Converts each value to a string.
2. Strips whitespace.
3. Skips empty strings.
4. Dedupes case-insensitively.
5. Returns the original first-seen text.

Example:

```python
_unique(["ER-1", " er-1 ", "ER-2"])
```

returns:

```python
["ER-1", "ER-2"]
```

## End-to-End Example

Suppose semantic catalogue search returns:

```text
1. VS-A / Customer Onboarding / score 1.30
2. VS-B / Billing Operations / score 1.10
3. VS-C / Identity Access / score 0.92
```

And historical retrieval returns two similar tickets:

```text
Historical ticket ER-10, score 0.82
  - VS-A / Customer Onboarding / direct / evidence "Similar onboarding request"
  - VS-D / Account Maintenance / implied / evidence "Account update dependency"

Historical ticket ER-11, score 0.74
  - VS-A / Customer Onboarding / direct / evidence "Prior onboarding workflow"
```

### After `build_candidates`

The merger creates candidates keyed by value-stream ID:

```text
VS-A Customer Onboarding
  from_semantic = True
  from_historical = True
  semantic_score = 1.30
  semantic_rank = 1
  supporting_ticket_count = 2
  direct_count = 2
  implied_count = 0
  best_support_score = 0.82
  avg_support_score = 0.78
  weighted_support = 2.0
  source_ticket_ids = ["ER-10", "ER-11"]
  evidence = ["Similar onboarding request", "Prior onboarding workflow"]
  lane = "semantic_plus_historic"

VS-B Billing Operations
  from_semantic = True
  from_historical = False
  semantic_score = 1.10
  semantic_rank = 2
  lane = "semantic_only"

VS-C Identity Access
  from_semantic = True
  from_historical = False
  semantic_score = 0.92
  semantic_rank = 3
  lane = "semantic_only"

VS-D Account Maintenance
  from_semantic = False
  from_historical = True
  supporting_ticket_count = 1
  direct_count = 0
  implied_count = 1
  best_support_score = 0.82
  weighted_support = 1.0
  source_ticket_ids = ["ER-10"]
  evidence = ["Account update dependency"]
  lane = "historic_only"
```

### After `select_review_pool`

Using the default policy:

```python
window = 18
max_semantic_plus_historic = 18
max_historic_only = 6
max_semantic_only = 3
semantic_min_score = 1.00
historic_min_hits = 1
```

The lanes are processed in priority order.

First, `semantic_plus_historic`:

```text
VS-A is included.
```

Then, `historic_only`:

```text
VS-D passes because supporting_ticket_count is 1.
VS-D is included.
```

Then, `semantic_only`:

```text
VS-B passes because semantic_score is 1.10.
VS-B is included.

VS-C fails because semantic_score is 0.92, below the 1.00 threshold.
VS-C is excluded.
```

Final review pool:

```text
1. VS-A Customer Onboarding       semantic_plus_historic
2. VS-D Account Maintenance       historic_only
3. VS-B Billing Operations        semantic_only
```

This is the set sent forward to the review-pool LLM step.

## Flow Summary

```text
semantic catalogue hits
        +
historical ticket hits
        |
        v
build_candidates
        |
        |-- merge by value_stream_id
        |-- attach semantic score/rank
        |-- aggregate historical ticket support
        |-- compute direct/implied counts
        |-- compute best/avg/weighted support
        |-- assign lane
        v
all merged candidates
        |
        v
select_review_pool
        |
        |-- rank semantic_plus_historic
        |-- gate/rank historic_only
        |-- gate/rank semantic_only
        |-- fill pool in lane priority order
        |-- enforce total window
        v
bounded review pool for LLM selection
```

