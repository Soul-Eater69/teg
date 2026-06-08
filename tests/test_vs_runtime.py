"""derive_runtime: fetch sizes + merge policy adapt to the requested count."""

from __future__ import annotations

from teg.value_stream.candidate_merger import derive_runtime


def test_default_request_matches_production_window() -> None:
    vs_top_k, historical_top_k, policy = derive_runtime(10)
    assert (vs_top_k, historical_top_k) == (50, 6)
    assert policy.window == 18
    assert policy.max_semantic_plus_historic == 18
    assert policy.max_historic_only == 6
    assert policy.max_semantic_only == 3
    assert policy.max_supporting_tickets == 2


def test_large_request_expands_window_floored_at_requested() -> None:
    vs_top_k, _, policy = derive_runtime(25)
    assert vs_top_k == 50  # capped at the catalogue
    assert policy.window == 25  # floored at requested
    assert policy.max_semantic_plus_historic == 25
    assert policy.max_semantic_only == 5  # min(5, max(3, floor(25*0.20)))


def test_small_request_floors_window_at_18() -> None:
    _, _, policy = derive_runtime(4)
    assert policy.window == 18
    assert policy.max_semantic_only == 3
