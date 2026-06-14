"""Reference-free description judges: faithfulness + coverage (fake LLM)."""

from __future__ import annotations

import asyncio

from teg.theme.description_judges import (
    CoverageResult,
    FaithfulnessResult,
    judge_coverage,
    judge_faithfulness,
)


class FaithLLM:
    async def complete(self, *, system, user, schema):
        return FaithfulnessResult(claims=[
            {"claim": "expands CPS field sizes", "supported": True},
            {"claim": "will launch in Q3", "supported": False},  # invented
        ])


class CoverageLLM:
    async def complete(self, *, system, user, schema):
        return CoverageResult(facts=[
            {"fact": "expand field sizes to 11 digits", "covered": True},
            {"fact": "across multiple CPS platforms", "covered": False},  # omitted
        ])


def test_faithfulness_score_and_unsupported() -> None:
    out = asyncio.run(judge_faithfulness(description="d", source="s", llm_client=FaithLLM()))
    assert out.score() == 0.5  # 1 of 2 supported
    assert out.unsupported() == ["will launch in Q3"]


def test_faithfulness_empty_description_is_perfect() -> None:
    out = asyncio.run(judge_faithfulness(description="  ", source="s", llm_client=FaithLLM()))
    assert out.score() == 1.0 and out.claims == []  # no claims -> nothing unfaithful


def test_coverage_score_and_missed() -> None:
    out = asyncio.run(judge_coverage(description="d", source="s", llm_client=CoverageLLM()))
    assert out.score() == 0.5  # 1 of 2 covered
    assert out.missed() == ["across multiple CPS platforms"]


def test_coverage_empty_source_is_perfect() -> None:
    out = asyncio.run(judge_coverage(description="d", source="  ", llm_client=CoverageLLM()))
    assert out.score() == 1.0  # no key facts to cover
