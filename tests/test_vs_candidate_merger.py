"""Candidate merger tests: building/aggregation (T5) + gating/caps/ranking (T6)."""

from __future__ import annotations

from teg.integrations.search import HistoricalHit, HistoricalValueStreamLabel, ValueStreamHit
from teg.value_stream.candidate_merger import build_candidates, select_review_pool
from teg.value_stream.models import CandidateMergePolicy, ValueStreamCandidate


def _label(vs_id, name, support_type="implied", reason="", evidence=""):
    return HistoricalValueStreamLabel(vs_id, name, support_type, reason, evidence)


# ---- T5: build_candidates ------------------------------------------------

def test_lane_assignment_across_both_lanes() -> None:
    vs_hits = [
        ValueStreamHit("VS1", "Adjudicate Claim", score=1.4),
        ValueStreamHit("VS2", "Receive Care", score=1.1),
    ]
    hist = [
        HistoricalHit("IDMT-1", "t1", score=0.82, value_streams=[_label("VS1", "Adjudicate Claim", "direct")]),
        HistoricalHit("IDMT-2", "t2", score=0.61, value_streams=[_label("VS3", "Issue Payment", "implied")]),
    ]
    by_id = {c.value_stream_id: c for c in build_candidates(vs_hits, hist)}
    assert by_id["VS1"].lane == "semantic_plus_historic"
    assert by_id["VS2"].lane == "semantic_only"
    assert by_id["VS3"].lane == "historic_only"


def test_historical_aggregation_counts_and_scores() -> None:
    hist = [
        HistoricalHit("IDMT-1", "t1", score=0.82, value_streams=[_label("VS1", "Adjudicate Claim", "direct", evidence="claims")]),
        HistoricalHit("IDMT-2", "t2", score=0.72, value_streams=[_label("VS1", "Adjudicate Claim", "implied")]),
        HistoricalHit("IDMT-1", "t1", score=0.82, value_streams=[_label("VS1", "Adjudicate Claim", "direct")]),
    ]
    candidate = build_candidates([], hist)[0]
    assert candidate.supporting_ticket_count == 2
    assert candidate.direct_count == 2
    assert candidate.implied_count == 1
    assert candidate.best_support_score == 0.82
    assert candidate.weighted_support == 2.0
    assert candidate.evidence == ["claims"]


# ---- T6: select_review_pool ----------------------------------------------

def _cand(vs_id, lane, *, semantic=0.0, hits=0, direct=0, best=0.0, weighted=0.0, name=None):
    return ValueStreamCandidate(
        value_stream_id=vs_id,
        value_stream_name=name or vs_id,
        from_semantic=lane != "historic_only",
        from_historical=lane != "semantic_only",
        semantic_score=semantic,
        supporting_ticket_count=hits,
        direct_count=direct,
        best_support_score=best,
        weighted_support=weighted,
        lane=lane,
    )


def test_qualified_candidates_rank_ahead_of_backfill() -> None:
    # The semantic floor prioritises the strong candidate; the weak one is not
    # excluded, just backfilled after - so the review pool stays full.
    pool = select_review_pool(
        [_cand("WEAK", "semantic_only", semantic=0.5), _cand("STRONG", "semantic_only", semantic=1.5)]
    )
    assert [c.value_stream_id for c in pool] == ["STRONG", "WEAK"]


def test_gate_drops_weak_only_when_window_overflows() -> None:
    # One slot: the gate decides who makes the cut (qualified wins).
    policy = CandidateMergePolicy(window=1, max_semantic_only=3)
    pool = select_review_pool(
        [_cand("WEAK", "semantic_only", semantic=0.5), _cand("STRONG", "semantic_only", semantic=1.5)],
        policy=policy,
    )
    assert [c.value_stream_id for c in pool] == ["STRONG"]


def test_backfill_fills_window_when_historic_absent() -> None:
    # Failure mode: no historic hits and every semantic score below the floor.
    # Greedy backfill must still fill the window instead of returning almost nothing.
    cands = [_cand(f"VS{i}", "semantic_only", semantic=0.4) for i in range(25)]
    pool = select_review_pool(cands)
    assert len(pool) == 18  # window filled despite all candidates being sub-threshold


def test_thin_historic_kept_when_nothing_else_to_fill_with() -> None:
    thin = _cand("VS1", "historic_only", hits=1, direct=0, best=0.5, weighted=0.4)
    strict = CandidateMergePolicy(historic_min_hits=2, historic_min_best=0.9, historic_min_weighted=0.9)
    # Gated out of the preferred fill, but backfilled since the pool would be empty.
    assert [c.value_stream_id for c in select_review_pool([thin], policy=strict)] == ["VS1"]


def test_lane_priority_and_window_cap() -> None:
    cands = [_cand(f"S{i}", "semantic_plus_historic", semantic=2.0 - i * 0.01, hits=1) for i in range(20)]
    cands += [_cand("H1", "historic_only", hits=2, best=0.8, weighted=1.0)]
    cands += [_cand("M1", "semantic_only", semantic=1.5)]
    pool = select_review_pool(cands)
    assert len(pool) == 18  # window cap
    assert all(c.lane == "semantic_plus_historic" for c in pool)  # top lane fills it


def test_lanes_ordered_when_room() -> None:
    cands = [
        _cand("S1", "semantic_plus_historic", semantic=2.0, hits=1),
        _cand("H1", "historic_only", hits=2, best=0.8, weighted=1.0),
        _cand("M1", "semantic_only", semantic=1.5),
    ]
    assert [c.value_stream_id for c in select_review_pool(cands)] == ["S1", "H1", "M1"]
