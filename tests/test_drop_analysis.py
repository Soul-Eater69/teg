"""Displacement / bias analysis of dropped GT (Level A, deterministic)."""

from __future__ import annotations

from teg.value_stream.drop_analysis import analyze_drops


def test_swap_counts_and_rates() -> None:
    # Ticket 1: GT={A,B}, picked={A,X} -> B dropped, X wrong (a B->X swap).
    # Ticket 2: GT={A,C}, picked={A,X} -> C dropped, X wrong (a C->X swap).
    tickets = [({"A", "B"}, ["A", "X"]), ({"A", "C"}, ["A", "X"])]
    a = analyze_drops(tickets)

    assert a.total_fn == 2 and a.total_fp == 2  # equal at exact count
    assert a.per_vs["A"].gt_count == 2 and a.per_vs["A"].fn_count == 0  # A always GT, never dropped
    assert a.per_vs["B"].drop_rate == 1.0  # B was GT once, dropped once
    assert a.per_vs["X"].fp_count == 2 and a.per_vs["X"].gt_count == 0  # X over-picked, never GT
    # X is the chronic over-pick.
    assert a.most_overpicked(1)[0].vs_id == "X"
    # Confusions: B->X and C->X each once.
    assert dict(a.confusion) == {("B", "X"): 1, ("C", "X"): 1}


def test_most_dropped_needs_min_appearances() -> None:
    # D is GT 3x and dropped each time; E is GT once (below the >=3 floor) -> only D ranks.
    tickets = [
        ({"D"}, ["Z"]), ({"D"}, ["Z"]), ({"D"}, ["Z"]),
        ({"E"}, ["Z"]),
    ]
    a = analyze_drops(tickets)
    dropped = a.most_dropped()
    assert [s.vs_id for s in dropped] == ["D"]  # E excluded (only 1 GT appearance)
    assert dropped[0].drop_rate == 1.0


def test_popularity_bias_when_picks_are_more_common() -> None:
    # The wrong pick P is a high-base-rate VS; the dropped GT G is rare -> popularity bias.
    base_rates = {"P": 0.40, "G": 0.05, "A": 0.30}
    tickets = [({"A", "G"}, ["A", "P"])]  # G dropped, P picked instead
    a = analyze_drops(tickets, base_rates=base_rates)
    assert a.mean_base_rate_overpicked == 0.40  # P
    assert a.mean_base_rate_dropped == 0.05  # G
    assert a.mean_base_rate_overpicked > a.mean_base_rate_dropped
