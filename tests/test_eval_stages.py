"""Stage-eval scoring helpers + the traced batched selection (offline)."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.models import CatalogueStage
from teg.theme.stage_selection import (
    BatchedStageSelection,
    StageSelectionInput,
    select_stages_for_all_traced,
)

# eval_stages lives in scripts/ (not importable as a package); load it by path.
_spec = importlib.util.spec_from_file_location(
    "eval_stages", Path(__file__).resolve().parents[1] / "scripts" / "eval_stages.py"
)
eval_stages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_stages)


def test_score_pair() -> None:
    assert eval_stages.score_pair({"a", "b"}, {"b", "c"}) == (1, 1, 1)
    assert eval_stages.score_pair(set(), {"a"}) == (0, 0, 1)
    assert eval_stages.score_pair({"a"}, set()) == (0, 1, 0)


def test_mislink_counts_separates_cross_vs_from_invalid() -> None:
    stages_by_vs = {"VS1": {"S1", "S2"}, "VS2": {"S3", "S4"}}
    raw_picks = {
        "VS1": ["S1", "S3", "S9"],  # S1 ok, S3 belongs to VS2 (cross), S9 invalid
        "VS2": ["S4"],              # ok
    }
    out = eval_stages.mislink_counts(raw_picks, stages_by_vs)
    assert out == {"total_picks": 4, "foreign": 2, "cross_vs": 1, "invalid": 1}


def test_aggregate_micro_macro_and_mislink() -> None:
    pairs = [
        {"tp": 1, "fp": 1, "fn": 0, "fallback": 0, "n_pred": 2, "n_gt": 1},
        {"tp": 1, "fp": 0, "fn": 1, "fallback": 0, "n_pred": 1, "n_gt": 2},
    ]
    agg = eval_stages._aggregate(pairs, [{"total_picks": 3, "foreign": 1, "cross_vs": 1, "invalid": 0}])
    assert agg["micro"]["precision"] == round(2 / 3, 4)  # tp=2, fp=1
    assert agg["micro"]["recall"] == round(2 / 3, 4)  # tp=2, fn=1
    assert agg["mislink"]["mislink_rate"] == round(1 / 3, 4)


def _stage(sid: str, name: str) -> CatalogueStage:
    return CatalogueStage(stage_id=sid, stage_name=name, stage_description="", sequence=0,
                          entrance_criteria="", exit_criteria="", value_items="", active=True,
                          created_date="", modified_date="")


class FakeLLM:
    """Returns a fixed BatchedStageSelection, incl. a stage_id foreign to its VS."""

    async def complete(self, *, system, user, schema):
        return BatchedStageSelection(value_streams=[
            {"valueStreamId": "VS1", "selectedStages": [
                {"stageId": "S1"}, {"stageId": "S3"}]},  # S3 is VS2's stage -> mislink
            {"valueStreamId": "VS2", "selectedStages": [{"stageId": "S3"}]},
        ])


def test_select_stages_for_all_traced_returns_raw_picks() -> None:
    ctx = CondensedContext(
        summary_fields=SummaryFields(generated_summary="x", business_problem="", business_capability=""),
        generation_signals=GenerationSignals(),
    )
    inputs = [
        StageSelectionInput(ApprovedValueStream(value_stream_id="VS1", value_stream_name="One"),
                            "", "", [_stage("S1", "Alpha"), _stage("S2", "Beta")]),
        StageSelectionInput(ApprovedValueStream(value_stream_id="VS2", value_stream_name="Two"),
                            "", "", [_stage("S3", "Gamma")]),
    ]
    resolved, raw = asyncio.run(
        select_stages_for_all_traced(condensed=ctx, inputs=inputs, llm_client=FakeLLM()))

    # Resolved drops the foreign S3 from VS1; raw keeps it so mislinking is measurable.
    assert [s.stage_id for s in resolved["VS1"]] == ["S1"]
    assert raw["VS1"] == ["S1", "S3"]
    assert raw["VS2"] == ["S3"]
