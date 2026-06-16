"""Reference-free judges: claim extraction + faithfulness/correctness + coverage (fake LLM)."""

from __future__ import annotations

import asyncio

from teg.theme.description_judges import (
    ClaimList,
    CorrectnessResult,
    CoverageResult,
    FaithfulnessResult,
    extract_claims,
    judge_correctness,
    judge_coverage,
    judge_faithfulness,
)


class ClaimsLLM:
    async def complete(self, *, system, user, schema):
        return ClaimList(claims=["expands CPS field sizes", "will launch in Q3", "  "])


class FaithLLM:
    async def complete(self, *, system, user, schema):
        return FaithfulnessResult(claims=[
            {"claim": "expands CPS field sizes", "supported": True},
            {"claim": "will launch in Q3", "supported": False},  # invented
        ])


class CorrectLLM:
    async def complete(self, *, system, user, schema):
        return CorrectnessResult(claims=[
            {"claim": "expands CPS field sizes", "correct": True},
            {"claim": "will launch in Q3", "correct": False},  # distorted/unverifiable detail
        ])


class CoverageLLM:
    async def complete(self, *, system, user, schema):
        return CoverageResult(facts=[
            {"fact": "expand field sizes to 11 digits", "covered": True},
            {"fact": "across multiple CPS platforms", "covered": False},  # omitted
        ])


def test_extract_claims_drops_blank() -> None:
    out = asyncio.run(extract_claims(text="d", llm_client=ClaimsLLM()))
    assert out == ["expands CPS field sizes", "will launch in Q3"]  # blank dropped


def test_extract_claims_empty_text() -> None:
    assert asyncio.run(extract_claims(text="  ", llm_client=ClaimsLLM())) == []


def test_faithfulness_score_and_unsupported() -> None:
    out = asyncio.run(judge_faithfulness(claims=["a", "b"], source="s", llm_client=FaithLLM()))
    assert out.score() == 0.5  # 1 of 2 supported
    assert out.unsupported() == ["will launch in Q3"]


def test_faithfulness_no_claims_is_perfect() -> None:
    out = asyncio.run(judge_faithfulness(claims=[], source="s", llm_client=FaithLLM()))
    assert out.score() == 1.0 and out.claims == []  # no claims -> nothing unfaithful


def test_correctness_score_and_incorrect() -> None:
    out = asyncio.run(judge_correctness(claims=["a", "b"], source="s", llm_client=CorrectLLM()))
    assert out.score() == 0.5
    assert out.incorrect() == ["will launch in Q3"]


def test_coverage_score_and_missed() -> None:
    out = asyncio.run(judge_coverage(description="d", source="s", llm_client=CoverageLLM()))
    assert out.score() == 0.5  # 1 of 2 covered
    assert out.missed() == ["across multiple CPS platforms"]


def test_coverage_empty_source_is_perfect() -> None:
    out = asyncio.run(judge_coverage(description="d", source="  ", llm_client=CoverageLLM()))
    assert out.score() == 1.0  # no key facts to cover
