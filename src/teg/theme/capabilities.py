"""L3 (and derived L2) capability prediction for the selected stages of one value stream.

Runs in parallel with business needs, after stage selection. Each catalogue stage carries its
governed L3 capabilities (each with its L2 parent inline). ONE batched call covers all of the
value stream's selected stages - for each stage the LLM picks the applicable L3 capabilities
from THAT stage's governed candidates only (no invention, no cross-stage borrowing); each
selected L3 maps 1-1 to its L2, so the L2 list is derived as the unique parents. Returns
(l3_capabilities, l2_capabilities), one StageCapabilities entry per stage.
"""

from __future__ import annotations

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
from teg.theme.stage_catalogue import render_candidate_stages

_CAPABILITY_SIGNALS = ["businessSolutionObjectives"]


class CapabilitySelectionItem(CamelModel):
    capability_id: str
    capability_name: str = ""  # echoed for anchoring; the catalogue name stays canonical
    reason: str = ""


class StageCapabilitySelection(CamelModel):
    """One stage's selected L3 capabilities (a batched-output entry)."""

    stage_id: str
    capabilities: list[CapabilitySelectionItem] = Field(default_factory=list)


class BatchedCapabilitySelection(CamelModel):
    """The selection LLM's structured output: one entry per selected stage."""

    stages: list[StageCapabilitySelection] = Field(default_factory=list)


async def generate_capabilities(
    *,
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    selected_stages: list[CatalogueStage],
    llm_client: LLMClient,
) -> tuple[list[StageCapabilities], list[StageCapabilities]]:
    active = [s for s in selected_stages if s.capabilities]  # a stage with no L3s has nothing
    if not active:
        return [], []

    prompt = load_prompt("theme/capability_selection")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        generation_signals=render_generation_signals(condensed, _CAPABILITY_SIGNALS),
        value_stream_name=value_stream.value_stream_name,
        value_stream_description=value_stream_description,
        stages="\n\n".join(_stage_block(s) for s in active),
    )
    result = await llm_client.complete(system=system, user=user, schema=BatchedCapabilitySelection)

    by_stage = {s.stage_id: s for s in result.stages}
    l3: list[StageCapabilities] = []
    l2: list[StageCapabilities] = []
    for stage in active:
        stage_l3, stage_l2 = _resolve(by_stage.get(stage.stage_id), stage)
        l3.append(stage_l3)
        l2.append(stage_l2)
    return l3, l2


async def generate_capabilities_traced(
    *,
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    selected_stages: list[CatalogueStage],
    llm_client: LLMClient,
) -> tuple[list[StageCapabilities], list[StageCapabilities], dict[str, list[str]]]:
    """Same batched L3/L2 selection, plus the LLM's RAW capability picks per stage (unresolved).

    The third value is ``{stage_id: [picked capability_id, ...]}`` exactly as the LLM returned it,
    BEFORE :func:`_resolve` drops ids foreign to that stage - so eval can measure cross-STAGE
    mislinking (an L3 the batched call put under the wrong stage). Falls back to the plain call's
    resolution; the raw picks come from the same LLM result.
    """
    active = [s for s in selected_stages if s.capabilities]
    if not active:
        return [], [], {}

    prompt = load_prompt("theme/capability_selection")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        generation_signals=render_generation_signals(condensed, _CAPABILITY_SIGNALS),
        value_stream_name=value_stream.value_stream_name,
        value_stream_description=value_stream_description,
        stages="\n\n".join(_stage_block(s) for s in active),
    )
    result = await llm_client.complete(system=system, user=user, schema=BatchedCapabilitySelection)

    by_stage = {s.stage_id: s for s in result.stages}
    l3: list[StageCapabilities] = []
    l2: list[StageCapabilities] = []
    raw_picks: dict[str, list[str]] = {}
    for stage in active:
        entry = by_stage.get(stage.stage_id)
        stage_l3, stage_l2 = _resolve(entry, stage)
        l3.append(stage_l3)
        l2.append(stage_l2)
        raw_picks[stage.stage_id] = [c.capability_id for c in (entry.capabilities if entry else [])]
    return l3, l2, raw_picks


def _stage_block(stage: CatalogueStage) -> str:
    return (
        f"### Stage {stage.stage_id}\n"
        + render_candidate_stages([stage])  # name, description, entrance/exit, value items
        + "\nCandidate L3 capabilities (choose by id; each shows its parent L2):\n"
        + _render_candidates(stage.capabilities)
    )


def _resolve(
    result: StageCapabilitySelection | None, stage: CatalogueStage
) -> tuple[StageCapabilities, StageCapabilities]:
    by_id = {c.capability_id: c for c in stage.capabilities}
    l3: list[Capability] = []
    l2_by_id: dict[str, Capability] = {}  # unique L2 parents (1-1 with the selected L3)
    seen: set[str] = set()
    for item in result.capabilities if result else []:
        cap = by_id.get(item.capability_id)
        if cap is None or cap.capability_id in seen:  # only this stage's governed L3, deduped
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
        + (f" [tier: {c.tier}]" if c.tier else "")
        + (f" (L2: {c.level_two_name})" if c.level_two_name else "")
        for c in capabilities
    )
