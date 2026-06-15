"""Stage-usage judge for Business Needs (fake LLM)."""

from __future__ import annotations

import asyncio

from teg.ingestion.catalogues.models import CatalogueStage
from teg.theme.business_needs_judges import StageUsageResult, judge_stage_usage


def _stage(sid: str, name: str) -> CatalogueStage:
    return CatalogueStage(stage_id=sid, stage_name=name, stage_description="d", sequence=1,
                          entrance_criteria="", exit_criteria="", value_items="", active=True,
                          created_date="", modified_date="")


class UsageLLM:
    async def complete(self, *, system, user, schema):
        return StageUsageResult(stages=[
            {"stageId": "S1", "addressed": True, "aligned": True},
            {"stageId": "S2", "addressed": True, "aligned": False},  # addressed but misfiled
            {"stageId": "S3", "addressed": False, "aligned": False},  # missing entirely
        ])


def test_usage_alignment_unused_misaligned() -> None:
    stages = [_stage("S1", "A"), _stage("S2", "B"), _stage("S3", "C")]
    out = asyncio.run(judge_stage_usage(business_needs="doc", stages=stages, llm_client=UsageLLM()))
    assert out.usage() == 2 / 3  # 2 of 3 addressed
    assert out.alignment() == 0.5  # of the 2 addressed, 1 aligned
    assert out.unused() == ["S3"]
    assert out.misaligned() == ["S2"]


def test_empty_inputs_are_perfect() -> None:
    out = asyncio.run(judge_stage_usage(business_needs="", stages=[_stage("S1", "A")], llm_client=UsageLLM()))
    assert out.usage() == 1.0 and out.alignment() == 1.0  # nothing to judge
