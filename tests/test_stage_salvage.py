"""Cross-VS mislink salvage: a stage put under the wrong value stream is reassigned to its owner."""

from __future__ import annotations

import asyncio

from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.models import CatalogueStage
from teg.theme.stage_selection import (
    BatchedStageSelection,
    StageSelectionInput,
    select_stages_for_all_traced,
)


def _stage(sid: str, name: str) -> CatalogueStage:
    return CatalogueStage(stage_id=sid, stage_name=name, stage_description="", sequence=1,
                          entrance_criteria="", exit_criteria="", value_items="", active=True,
                          created_date="", modified_date="")


def _ctx() -> CondensedContext:
    return CondensedContext(
        summary_fields=SummaryFields(generated_summary="x", business_problem="", business_capability=""),
        generation_signals=GenerationSignals())


class MislinkLLM:
    """Puts S3 (VS2's stage) wrongly under VS1; correctly picks S1 for VS1 and nothing for VS2."""

    async def complete(self, *, system, user, schema):
        return BatchedStageSelection(value_streams=[
            {"valueStreamId": "VS1", "selectedStages": [{"stageId": "S1"}, {"stageId": "S3"}]},
            {"valueStreamId": "VS2", "selectedStages": []},
        ])


def test_mislinked_stage_is_salvaged_to_its_owner() -> None:
    inputs = [
        StageSelectionInput(ApprovedValueStream(value_stream_id="VS1", value_stream_name="One"),
                            "", "", [_stage("S1", "A"), _stage("S2", "B")]),
        StageSelectionInput(ApprovedValueStream(value_stream_id="VS2", value_stream_name="Two"),
                            "", "", [_stage("S3", "C")]),
    ]
    resolved, raw = asyncio.run(
        select_stages_for_all_traced(condensed=_ctx(), inputs=inputs, llm_client=MislinkLLM()))

    # VS1 keeps only its own S1 (foreign S3 dropped from VS1).
    assert [s.stage_id for s in resolved["VS1"]] == ["S1"]
    # S3 is SALVAGED to its true owner VS2 (instead of being lost).
    assert [s.stage_id for s in resolved["VS2"]] == ["S3"]
    # raw_picks still reflects the model's RAW behaviour (so the mislink metric is unaffected).
    assert raw["VS1"] == ["S1", "S3"]
