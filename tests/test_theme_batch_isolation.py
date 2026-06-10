"""Batched stage + capability selection must not cross-link owners.

Stages and capabilities are picked for many owners in one call (all VS in one stage call; all of
a VS's stages in one capability call). These tests feed a model output that deliberately assigns
one owner's id to another and assert the resolver DROPS it (never mis-attributes), because each
owner's picks are validated only against its own governed candidate list.
"""

from __future__ import annotations

from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.models import CatalogueCapability, CatalogueStage
from teg.theme.capabilities import (
    BatchedCapabilitySelection,
    CapabilitySelectionItem,
    StageCapabilitySelection,
    generate_capabilities,
)
from teg.theme.stage_selection import (
    BatchedStageSelection,
    StageSelectionInput,
    StageSelectionItem,
    VsStageSelection,
    select_stages_for_all,
)


class _Fake:
    def __init__(self, payload):
        self._payload = payload

    async def complete(self, *, system, user, schema):
        return self._payload


def _cond() -> CondensedContext:
    return CondensedContext(
        summary_fields=SummaryFields(generated_summary="s", business_problem="p", business_capability="c"),
        generation_signals=GenerationSignals(),
    )


def _cap(cap_id: str) -> CatalogueCapability:
    return CatalogueCapability(
        capability_id=cap_id, capability_name=cap_id, capability_description="", level=3, tier="",
        active=True, level_one_id="L1", level_one_name="L1", level_two_id="L2", level_two_name="L2",
    )


def _stage(stage_id: str, caps=None) -> CatalogueStage:
    return CatalogueStage(
        stage_id=stage_id, stage_name=stage_id, stage_description="", sequence=1,
        entrance_criteria="", exit_criteria="", value_items="", active=True,
        created_date="", modified_date="", capabilities=caps or [],
    )


async def test_stage_selection_drops_cross_vs_stage() -> None:
    vs_a = ApprovedValueStream(value_stream_id="VSR1", value_stream_name="A")
    vs_b = ApprovedValueStream(value_stream_id="VSR2", value_stream_name="B")
    inputs = [
        StageSelectionInput(vs_a, "descA", "", [_stage("VSS1")]),  # VSS1 belongs to VSR1
        StageSelectionInput(vs_b, "descB", "", [_stage("VSS2")]),  # VSS2 belongs to VSR2
    ]
    # Model wrongly puts VSR2's stage (VSS2) under VSR1.
    payload = BatchedStageSelection(value_streams=[
        VsStageSelection(value_stream_id="VSR1", selected_stages=[StageSelectionItem(stage_id="VSS2")]),
        VsStageSelection(value_stream_id="VSR2", selected_stages=[StageSelectionItem(stage_id="VSS2")]),
    ])
    result = await select_stages_for_all(condensed=_cond(), inputs=inputs, llm_client=_Fake(payload))

    # VSR1 must NOT receive VSS2; the cross-VS id is dropped, so VSR1 falls back to its own stage.
    assert [s.stage_id for s in result["VSR1"]] == ["VSS1"]
    assert [s.stage_id for s in result["VSR2"]] == ["VSS2"]


async def test_capabilities_drop_cross_stage_capability() -> None:
    vs = ApprovedValueStream(value_stream_id="VSR1", value_stream_name="A")
    stage1 = _stage("VSS1", caps=[_cap("CAP-A")])  # CAP-A belongs to VSS1
    stage2 = _stage("VSS2", caps=[_cap("CAP-B")])  # CAP-B belongs to VSS2
    # Model wrongly puts VSS2's capability (CAP-B) under VSS1.
    payload = BatchedCapabilitySelection(stages=[
        StageCapabilitySelection(stage_id="VSS1", capabilities=[CapabilitySelectionItem(capability_id="CAP-B")]),
        StageCapabilitySelection(stage_id="VSS2", capabilities=[CapabilitySelectionItem(capability_id="CAP-B")]),
    ])
    l3, _ = await generate_capabilities(
        condensed=_cond(), value_stream=vs, value_stream_description="d",
        selected_stages=[stage1, stage2], llm_client=_Fake(payload),
    )

    by_stage = {sc.stage_id: sc for sc in l3}
    # VSS1 must NOT receive CAP-B (cross-stage id dropped); VSS2 keeps its own CAP-B.
    assert [c.capability_id for c in by_stage["VSS1"].capabilities] == []
    assert [c.capability_id for c in by_stage["VSS2"].capabilities] == ["CAP-B"]
