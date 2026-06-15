"""L3 drop grounding probe (fake LLM)."""

from __future__ import annotations

import asyncio

from teg.ingestion.catalogues.models import CatalogueCapability
from teg.theme.l3_drop_explainer import L3GroundingExplanations, classify_l3_drop_grounding


def _cap(cid: str, name: str) -> CatalogueCapability:
    return CatalogueCapability(capability_id=cid, capability_name=name, capability_description="d",
                               level=3, tier="", active=True, level_one_id="L1", level_one_name="One",
                               level_two_id="L2", level_two_name="Two")


class FakeLLM:
    async def complete(self, *, system, user, schema):
        return L3GroundingExplanations(explanations=[
            {"capabilityId": "C2", "grounding": "context_present_but_dropped", "note": "card mentions X"},
        ])


def test_classify_l3_drop_grounding() -> None:
    caps = [_cap("C1", "A"), _cap("C2", "B")]
    out = asyncio.run(classify_l3_drop_grounding(
        ticket_context="t", stage_name="S", candidates=caps, dropped_ids=["C2"], llm_client=FakeLLM()))
    assert out["C2"].grounding == "context_present_but_dropped"


def test_empty_dropped_is_noop() -> None:
    out = asyncio.run(classify_l3_drop_grounding(
        ticket_context="t", stage_name="S", candidates=[_cap("C1", "A")], dropped_ids=[],
        llm_client=FakeLLM()))
    assert out == {}
