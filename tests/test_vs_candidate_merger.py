"""Candidate building tests: lane assignment + historical aggregation."""

from __future__ import annotations

from teg.integrations.search import HistoricalHit, HistoricalValueStreamLabel, ValueStreamHit
from teg.value_stream.candidate_merger import build_candidates


def _label(vs_id, name, support_type="implied", reason="", evidence=""):
    return HistoricalValueStreamLabel(vs_id, name, support_type, reason, evidence)


def test_lane_assignment_across_both_lanes() -> None:
    vs_hits = [
        ValueStreamHit("VS1", "Adjudicate Claim", score=1.4),  # both lanes
        ValueStreamHit("VS2", "Receive Care", score=1.1),  # semantic only
    ]
    hist = [
        HistoricalHit("IDMT-1", "t1", score=0.82, value_streams=[_label("VS1", "Adjudicate Claim", "direct")]),
        HistoricalHit("IDMT-2", "t2", score=0.61, value_streams=[_label("VS3", "Issue Payment", "implied")]),
    ]
    by_id = {c.value_stream_id: c for c in build_candidates(vs_hits, hist)}

    assert by_id["VS1"].lane == "semantic_plus_historic"
    assert by_id["VS2"].lane == "semantic_only"
    assert by_id["VS3"].lane == "historic_only"  # only historical


def test_historical_aggregation_counts_and_scores() -> None:
    hist = [
        HistoricalHit("IDMT-1", "t1", score=0.82, value_streams=[_label("VS1", "Adjudicate Claim", "direct", evidence="claims")]),
        HistoricalHit("IDMT-2", "t2", score=0.72, value_streams=[_label("VS1", "Adjudicate Claim", "implied")]),
        HistoricalHit("IDMT-1", "t1", score=0.82, value_streams=[_label("VS1", "Adjudicate Claim", "direct")]),  # dup ticket
    ]
    candidate = build_candidates([], hist)[0]

    assert candidate.value_stream_id == "VS1"
    assert candidate.supporting_ticket_count == 2  # IDMT-1, IDMT-2 (dedup)
    assert candidate.direct_count == 2
    assert candidate.implied_count == 1
    assert candidate.best_support_score == 0.82  # max similarity
    # weighted = support_weight(0.82)=1.0 * 2 tickets
    assert candidate.weighted_support == 2.0
    assert candidate.evidence == ["claims"]


def test_semantic_signal_captured() -> None:
    candidate = build_candidates([ValueStreamHit("VS1", "n", score=1.3)], [])[0]
    assert candidate.from_semantic and not candidate.from_historical
    assert candidate.semantic_score == 1.3
    assert candidate.semantic_rank == 1
