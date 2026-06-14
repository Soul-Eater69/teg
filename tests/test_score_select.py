"""Two-stage score-then-select: independent scores -> deterministic top-N."""

from __future__ import annotations

import asyncio

from teg.value_stream.selection import CandidateScoring, score_and_select
from teg.value_stream.models import ValueStreamCandidate


def _cand(vs_id: str, name: str) -> ValueStreamCandidate:
    return ValueStreamCandidate(value_stream_id=vs_id, value_stream_name=name)


class FakeLLM:
    def __init__(self, scores: list[dict]) -> None:
        self._scores = scores

    async def complete(self, *, system, user, schema):
        return CandidateScoring(scores=self._scores)


def test_takes_top_n_by_score() -> None:
    cands = [_cand("A", "a"), _cand("B", "b"), _cand("C", "c"), _cand("D", "d")]
    llm = FakeLLM([{"entityId": "A", "score": 0.4}, {"entityId": "B", "score": 0.9},
                   {"entityId": "C", "score": 0.3}, {"entityId": "D", "score": 0.8}])
    out = asyncio.run(score_and_select(query="q", candidates=cands, requested_count=2, llm_client=llm))
    assert [r.value_stream_id for r in out] == ["B", "D"]  # top-2 by score
    assert out[0].confidence == 90.0  # score carried as confidence (0.9 -> 90)


def test_unscored_candidates_sink_below_scored() -> None:
    # Only A is scored; B and C are unscored -> A first, then B/C in original order.
    cands = [_cand("A", "a"), _cand("B", "b"), _cand("C", "c")]
    out = asyncio.run(score_and_select(
        query="q", candidates=cands, requested_count=2,
        llm_client=FakeLLM([{"entityId": "A", "score": 0.5}])))
    assert out[0].value_stream_id == "A"
    assert out[1].value_stream_id == "B"  # first unscored in original order


def test_ignores_ids_outside_the_candidate_list() -> None:
    cands = [_cand("A", "a"), _cand("B", "b")]
    out = asyncio.run(score_and_select(
        query="q", candidates=cands, requested_count=1,
        llm_client=FakeLLM([{"entityId": "ZZZ", "score": 0.99}, {"entityId": "B", "score": 0.6}])))
    assert [r.value_stream_id for r in out] == ["B"]  # ZZZ not in catalogue -> ignored
