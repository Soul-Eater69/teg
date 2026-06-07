"""Merge the two retrieval lanes into ranked candidates for the review pool.

Two steps:
  build_candidates - aggregate the historical hits' VS labels into per-VS support,
    union with the catalogue (semantic) hits, and assign each a lane/bucket.
  select_review_pool (next) - gate, penalize generic/risky streams, rank, and cap to
    the candidate window.

This file does not decide value-stream truth - it organizes evidence and bounds the
prompt. Thresholds live in CandidateMergePolicy so they can be eval-tuned.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from teg.domain.value_stream import Bucket
from teg.integrations.search import HistoricalHit, ValueStreamHit

_MAX_SUPPORTING_TICKETS = 3


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


def _support_weight(score: float) -> float:
    if score >= 0.80:
        return 1.0
    if score >= 0.70:
        return 0.6
    if score >= 0.60:
        return 0.3
    return 0.0


def _unique(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out
