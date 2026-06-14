"""Level B (score_candidates) + Level C (explain_swaps) drop probes, with a fake LLM."""

from __future__ import annotations

import asyncio

from teg.value_stream.drop_explainer import (
    CandidateScores,
    GroundingExplanations,
    SwapExplanations,
    classify_drop_grounding,
    explain_swaps,
    score_candidates,
)
from teg.value_stream.models import ValueStreamCandidate


def _cand(vs_id: str, name: str) -> ValueStreamCandidate:
    return ValueStreamCandidate(value_stream_id=vs_id, value_stream_name=name)


class FakeScoreLLM:
    async def complete(self, *, system, user, schema):
        return CandidateScores(scores=[
            {"entityId": "A", "score": 0.9}, {"entityId": "B", "score": 0.6},
            {"entityId": "C", "score": 0.7},
        ])


class FakeSwapLLM:
    async def complete(self, *, system, user, schema):
        return SwapExplanations(explanations=[
            {"droppedId": "C", "reasonCode": "dropped_too_broad", "note": "downstream"},
        ])


def test_score_candidates_returns_clamped_scores() -> None:
    pool = [_cand("A", "Alpha"), _cand("B", "Beta"), _cand("C", "Gamma")]
    scores = asyncio.run(score_candidates(query="t", review_pool=pool, llm_client=FakeScoreLLM()))
    assert scores == {"A": 0.9, "B": 0.6, "C": 0.7}
    # A dropped GT 'C' (0.7) scoring above a picked 'B' (0.6) is the near-miss signal the eval flags.
    assert scores["C"] > scores["B"]


def test_explain_swaps_maps_codes() -> None:
    pool = [_cand("A", "Alpha"), _cand("C", "Gamma")]
    out = asyncio.run(explain_swaps(
        query="t", review_pool=pool, picked_ids=["A"], dropped_ids=["C"], llm_client=FakeSwapLLM()))
    assert out["C"].reason_code == "dropped_too_broad"


def test_explain_swaps_empty_when_no_picks() -> None:
    pool = [_cand("C", "Gamma")]
    out = asyncio.run(explain_swaps(
        query="t", review_pool=pool, picked_ids=[], dropped_ids=["C"], llm_client=FakeSwapLLM()))
    assert out == {}


class FakeGroundLLM:
    async def complete(self, *, system, user, schema):
        return GroundingExplanations(explanations=[
            {"droppedId": "C", "grounding": "context_present_but_dropped", "note": "ticket says X"},
        ])


def test_classify_drop_grounding_buckets() -> None:
    pool = [_cand("A", "Alpha"), _cand("C", "Gamma")]
    out = asyncio.run(classify_drop_grounding(
        query="t", review_pool=pool, dropped_ids=["C"], llm_client=FakeGroundLLM()))
    assert out["C"].grounding == "context_present_but_dropped"  # the fixable bucket
    assert out["C"].note == "ticket says X"
