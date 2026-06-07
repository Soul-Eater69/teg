"""Merge the two retrieval lanes into a bounded, ranked review pool.

Two steps:
  build_candidates - aggregate the historical hits' VS labels into per-VS support,
    union with the catalogue (semantic) hits, and assign each a lane/bucket.
  select_review_pool - gate weak candidates, penalize generic/risky streams, rank,
    and fill the candidate window in priority order (semantic+historic, then
    historic-only, then semantic-only).

This file organizes evidence and bounds the prompt; it does not decide value-stream
truth. Thresholds live in CandidateMergePolicy so they can be eval-tuned.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from teg.domain.value_stream import Bucket
from teg.integrations.search import HistoricalHit, ValueStreamHit

_MAX_SUPPORTING_TICKETS = 3

# Streams with broad wording that overlap many idea cards, so they over-surface. Not
# banned (strong evidence still wins), but penalized so they don't crowd the window.
GENERIC_OR_RISKY_STREAMS = {
    "discover business insights",
    "promote community health",
    "administer quality management program",
    "receive care",
    "adjudicate claim",
    "fill and manage prescriptions",
    "manage producer operations",
    "align and execute it strategy",
    "develop mission, vision, and strategy",
}


@dataclass(frozen=True)
class CandidateMergePolicy:
    """Tuning knobs for the review pool. Defaults are the eval-winning config."""

    window: int = 18  # max candidates sent to the LLM
    max_semantic_plus_historic: int = 18
    max_historic_only: int = 6
    max_semantic_only: int = 3
    # historic-only gate: any one of these qualifies it
    historic_min_hits: int = 1
    historic_min_best: float = 0.55
    historic_min_weighted: float = 0.5
    # semantic-only gate (higher floor; generic/risky higher still)
    semantic_min_score: float = 1.00
    semantic_min_score_generic: float = 1.25
    # generic/risky penalties
    generic_sort_penalty: float = 0.20  # in the semantic+historic blend when hits are thin
    generic_penalty_hits_exempt: int = 3
    semantic_only_generic_penalty: float = 0.25


@dataclass
class ValueStreamCandidate:
    value_stream_id: str
    value_stream_name: str
    value_stream_description: str = ""
    from_semantic: bool = False
    from_historical: bool = False
    semantic_score: float = 0.0
    semantic_rank: int | None = None
    supporting_ticket_count: int = 0
    direct_count: int = 0
    implied_count: int = 0
    best_support_score: float = 0.0
    avg_support_score: float = 0.0
    weighted_support: float = 0.0
    source_ticket_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    lane: Bucket = "semantic_only"


def build_candidates(
    value_stream_hits: list[ValueStreamHit],
    historical_hits: list[HistoricalHit],
    *,
    max_supporting_tickets: int = _MAX_SUPPORTING_TICKETS,
) -> list[ValueStreamCandidate]:
    by_id: dict[str, ValueStreamCandidate] = {}

    for rank, hit in enumerate(value_stream_hits, start=1):
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

    for vs_id, pairs in _group_historical_by_vs(historical_hits).items():
        first_label = pairs[0][1]
        candidate = by_id.setdefault(
            vs_id,
            ValueStreamCandidate(
                value_stream_id=vs_id,
                value_stream_name=first_label.value_stream_name,
            ),
        )
        ticket_ids = _unique(hit.ticket_id for hit, _ in pairs if hit.ticket_id)
        scores = [hit.score for hit, _ in pairs]
        candidate.from_historical = True
        candidate.supporting_ticket_count = len(ticket_ids)
        candidate.source_ticket_ids = ticket_ids[:max_supporting_tickets]
        candidate.direct_count = sum(1 for _, label in pairs if label.support_type == "direct")
        candidate.implied_count = sum(1 for _, label in pairs if label.support_type == "implied")
        candidate.best_support_score = max(scores, default=0.0)
        candidate.avg_support_score = (sum(scores) / len(scores)) if scores else 0.0
        candidate.weighted_support = round(
            _support_weight(candidate.best_support_score) * candidate.supporting_ticket_count, 4
        )
        candidate.evidence = _unique(
            label.evidence or label.reason for _, label in pairs if (label.evidence or label.reason)
        )[:max_supporting_tickets]

    for candidate in by_id.values():
        candidate.lane = _lane(candidate)
    return list(by_id.values())


def select_review_pool(
    candidates: list[ValueStreamCandidate],
    *,
    policy: CandidateMergePolicy = CandidateMergePolicy(),
) -> list[ValueStreamCandidate]:
    """Gate, rank, and cap to the candidate window in priority order."""
    semantic_plus = sorted(
        (c for c in candidates if c.lane == "semantic_plus_historic"),
        key=lambda c: _sort_semantic_plus_historic(c, policy),
    )
    historic_only = sorted(
        (c for c in candidates if c.lane == "historic_only" and _is_good_historic_only(c, policy)),
        key=_sort_historic_only,
    )
    semantic_only = sorted(
        (c for c in candidates if c.lane == "semantic_only" and _is_strong_semantic_only(c, policy)),
        key=lambda c: _sort_semantic_only(c, policy),
    )

    pool: list[ValueStreamCandidate] = []
    pool += semantic_plus[: policy.max_semantic_plus_historic]
    room = max(0, policy.window - len(pool))
    pool += historic_only[: min(policy.max_historic_only, room)]
    room = max(0, policy.window - len(pool))
    pool += semantic_only[: min(policy.max_semantic_only, room)]
    return pool[: policy.window]


def _group_historical_by_vs(historical_hits):
    grouped: dict[str, list] = {}
    for hit in historical_hits:
        for label in hit.value_streams:
            if label.value_stream_id:
                grouped.setdefault(label.value_stream_id, []).append((hit, label))
    return grouped


def _lane(candidate: ValueStreamCandidate) -> Bucket:
    if candidate.from_semantic and candidate.from_historical:
        return "semantic_plus_historic"
    if candidate.from_semantic:
        return "semantic_only"
    return "historic_only"


def _is_good_historic_only(c: ValueStreamCandidate, policy: CandidateMergePolicy) -> bool:
    return (
        c.supporting_ticket_count >= policy.historic_min_hits
        or c.direct_count >= 1
        or c.best_support_score >= policy.historic_min_best
        or c.weighted_support >= policy.historic_min_weighted
    )


def _is_strong_semantic_only(c: ValueStreamCandidate, policy: CandidateMergePolicy) -> bool:
    if _is_generic(c.value_stream_name):
        return c.semantic_score >= policy.semantic_min_score_generic
    return c.semantic_score >= policy.semantic_min_score


def _sort_semantic_plus_historic(c: ValueStreamCandidate, policy: CandidateMergePolicy) -> tuple:
    # Blend semantic with historical signal so strong historical evidence isn't buried
    # under a marginally-better-semantic candidate with only one hit.
    boost = min(1.0, c.supporting_ticket_count / 10.0) * 0.20 + c.best_support_score * 0.15
    blended = c.semantic_score + boost
    if _is_generic(c.value_stream_name) and c.supporting_ticket_count < policy.generic_penalty_hits_exempt:
        blended -= policy.generic_sort_penalty
    return (
        -blended,
        -c.semantic_score,
        -c.best_support_score,
        -c.weighted_support,
        -c.supporting_ticket_count,
        c.value_stream_name.lower(),
    )


def _sort_semantic_only(c: ValueStreamCandidate, policy: CandidateMergePolicy) -> tuple:
    penalty = policy.semantic_only_generic_penalty if _is_generic(c.value_stream_name) else 0.0
    return (-(c.semantic_score - penalty), c.value_stream_name.lower())


def _sort_historic_only(c: ValueStreamCandidate) -> tuple:
    return (
        -c.best_support_score,
        -c.weighted_support,
        -c.direct_count,
        -c.supporting_ticket_count,
        -c.implied_count,
        -c.avg_support_score,
        c.value_stream_name.lower(),
    )


def _support_weight(score: float) -> float:
    if score >= 0.80:
        return 1.0
    if score >= 0.70:
        return 0.6
    if score >= 0.60:
        return 0.3
    return 0.0


def _is_generic(name: str) -> bool:
    return _norm(name) in GENERIC_OR_RISKY_STREAMS


def _norm(name: str) -> str:
    return " ".join(name.lower().replace("&", "and").split())


def _unique(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out
