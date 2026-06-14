"""Stage drop probes: grounding + swap, with a fake LLM."""

from __future__ import annotations

import asyncio

from teg.ingestion.catalogues.models import CatalogueStage
from teg.theme.stage_drop_explainer import (
    StageGroundingExplanations,
    StageSwapExplanations,
    classify_stage_drop_grounding,
    explain_stage_swaps,
)


def _stage(sid: str, name: str) -> CatalogueStage:
    return CatalogueStage(stage_id=sid, stage_name=name, stage_description="d", sequence=1,
                          entrance_criteria="", exit_criteria="", value_items="", active=True,
                          created_date="", modified_date="")


class FakeGroundLLM:
    async def complete(self, *, system, user, schema):
        return StageGroundingExplanations(explanations=[
            {"stageId": "ST2", "grounding": "context_present_but_dropped", "note": "card mentions X"},
        ])


class FakeSwapLLM:
    async def complete(self, *, system, user, schema):
        return StageSwapExplanations(explanations=[
            {"droppedId": "ST2", "reasonCode": "dropped_too_broad", "note": "adjacent"},
        ])


def test_grounding_classifies_dropped_stage() -> None:
    stages = [_stage("ST1", "Intake"), _stage("ST2", "Resolve")]
    out = asyncio.run(classify_stage_drop_grounding(
        ticket_context="t", value_stream_name="VS", stages=stages,
        dropped_ids=["ST2"], llm_client=FakeGroundLLM()))
    assert out["ST2"].grounding == "context_present_but_dropped"
    assert out["ST2"].note == "card mentions X"


def test_swap_needs_picks() -> None:
    stages = [_stage("ST2", "Resolve")]
    # No picks -> empty (nothing to compare against).
    assert asyncio.run(explain_stage_swaps(
        ticket_context="t", value_stream_name="VS", stages=stages,
        picked_ids=[], dropped_ids=["ST2"], llm_client=FakeSwapLLM())) == {}


def test_swap_maps_reason() -> None:
    stages = [_stage("ST1", "Intake"), _stage("ST2", "Resolve")]
    out = asyncio.run(explain_stage_swaps(
        ticket_context="t", value_stream_name="VS", stages=stages,
        picked_ids=["ST1"], dropped_ids=["ST2"], llm_client=FakeSwapLLM()))
    assert out["ST2"].reason_code == "dropped_too_broad"
