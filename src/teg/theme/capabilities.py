"""L3 (and derived L2) capability prediction for the selected stages.

Runs in parallel with business needs, after stage selection. Each catalogue stage carries
its governed L3 capabilities (each with its L2 parent inline). For each selected stage the
LLM picks the L3 capabilities that apply (from the governed candidates only - no invention);
each selected L3 maps 1-1 to its L2, so the L2 list is derived as the unique parents.
Returns (l3_capabilities, l2_capabilities), one StageCapabilities entry per stage.
"""

from __future__ import annotations

import asyncio

from pydantic import Field

from teg.contracts.theme_io import (
    ApprovedValueStream,
    Capability,
    CondensedContext,
    StageCapabilities,
)
from teg.domain.base import CamelModel
from teg.ingestion.catalogues.models import CatalogueCapability, CatalogueStage
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.theme.context import render_generation_signals, render_ticket_context

_CAPABILITY_SIGNALS = ["businessSolutionObjectives"]


class CapabilitySelectionItem(CamelModel):
    capability_id: str
    reason: str = ""


class CapabilitySelectionResult(CamelModel):
    """The selection LLM's structured output."""

    capabilities: list[CapabilitySelectionItem] = Field(default_factory=list)


async def generate_capabilities(
    *,
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    selected_stages: list[CatalogueStage],
    llm_client: LLMClient,
) -> tuple[list[StageCapabilities], list[StageCapabilities]]:
    pairs = await asyncio.gather(
        *(
            _for_stage(condensed, value_stream, value_stream_description, stage, llm_client)
            for stage in selected_stages
            if stage.capabilities
        )
    )
    l3 = [l3 for l3, _ in pairs]
    l2 = [l2 for _, l2 in pairs]
    return l3, l2


async def _for_stage(
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    stage: CatalogueStage,
    llm_client: LLMClient,
) -> tuple[StageCapabilities, StageCapabilities]:
    prompt = load_prompt("theme/capability_selection")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        generation_signals=render_generation_signals(condensed, _CAPABILITY_SIGNALS),
        value_stream_name=value_stream.value_stream_name,
        value_stream_description=value_stream_description,
        stage_name=stage.stage_name,
        stage_description=stage.stage_description,
        candidate_capabilities=_render_candidates(stage.capabilities),
    )
    result = await llm_client.complete(system=system, user=user, schema=CapabilitySelectionResult)
    return _resolve(result, stage)


def _resolve(
    result: CapabilitySelectionResult, stage: CatalogueStage
) -> tuple[StageCapabilities, StageCapabilities]:
    by_id = {c.capability_id: c for c in stage.capabilities}
    l3: list[Capability] = []
    l2_by_id: dict[str, Capability] = {}  # unique L2 parents (1-1 with the selected L3)
    seen: set[str] = set()
    for item in result.capabilities:
        cap = by_id.get(item.capability_id)
        if cap is None or cap.capability_id in seen:  # only governed L3, deduped
            continue
        seen.add(cap.capability_id)
        l3.append(Capability(capability_id=cap.capability_id, name=cap.capability_name, reason=item.reason))
        if cap.level_two_id and cap.level_two_id not in l2_by_id:
            l2_by_id[cap.level_two_id] = Capability(capability_id=cap.level_two_id, name=cap.level_two_name)

    head = {"stage_id": stage.stage_id, "stage_name": stage.stage_name}
    return (
        StageCapabilities(**head, capabilities=l3),
        StageCapabilities(**head, capabilities=list(l2_by_id.values())),
    )


def _render_candidates(capabilities: list[CatalogueCapability]) -> str:
    return "\n".join(
        f"- {c.capability_id} | {c.capability_name}"
        + (f" - {c.capability_description}" if c.capability_description else "")
        + (f" (L2: {c.level_two_name})" if c.level_two_name else "")
        for c in capabilities
    )
