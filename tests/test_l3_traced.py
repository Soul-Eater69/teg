"""L3 capability selection: traced variant returns raw picks (for cross-stage mislink)."""

from __future__ import annotations

import asyncio

from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.models import CatalogueCapability, CatalogueStage
from teg.theme.capabilities import BatchedCapabilitySelection, generate_capabilities_traced


def _cap(cid: str, name: str) -> CatalogueCapability:
    return CatalogueCapability(capability_id=cid, capability_name=name, capability_description="",
                               level=3, tier="", active=True, level_one_id="L1", level_one_name="One",
                               level_two_id="L2", level_two_name="Two")


def _stage(sid: str, caps) -> CatalogueStage:
    return CatalogueStage(stage_id=sid, stage_name=sid, stage_description="", sequence=1,
                          entrance_criteria="", exit_criteria="", value_items="", active=True,
                          created_date="", modified_date="", capabilities=caps)


def _ctx() -> CondensedContext:
    return CondensedContext(
        summary_fields=SummaryFields(generated_summary="x", business_problem="", business_capability=""),
        generation_signals=GenerationSignals())


class FakeLLM:
    """Puts C3 (stage S2's capability) wrongly under S1; picks C1 correctly for S1."""

    async def complete(self, *, system, user, schema):
        return BatchedCapabilitySelection(stages=[
            {"stageId": "S1", "capabilities": [{"capabilityId": "C1"}, {"capabilityId": "C3"}]},
            {"stageId": "S2", "capabilities": [{"capabilityId": "C3"}]},
        ])


def test_traced_resolves_and_exposes_raw_picks() -> None:
    stages = [_stage("S1", [_cap("C1", "A"), _cap("C2", "B")]), _stage("S2", [_cap("C3", "C")])]
    l3, _l2, raw = asyncio.run(generate_capabilities_traced(
        condensed=_ctx(), value_stream=ApprovedValueStream(value_stream_id="VS", value_stream_name="n"),
        value_stream_description="", selected_stages=stages, llm_client=FakeLLM()))

    by_stage = {sc.stage_id: [c.capability_id for c in sc.capabilities] for sc in l3}
    assert by_stage["S1"] == ["C1"]  # foreign C3 dropped from S1 by _resolve
    assert by_stage["S2"] == ["C3"]
    # raw picks keep the model's behaviour so mislink is measurable: C3 was put under S1.
    assert raw["S1"] == ["C1", "C3"]
