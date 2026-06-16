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
from teg.theme.context import render_ticket_context
from teg.theme.stage_catalogue import render_candidate_stages



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
    _salvage_mislinks(active, raw_picks, l3)
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
    _salvage_mislinks(active, raw_picks, l3)
    return l3, l2, raw_picks


def _salvage_mislinks(
    active: list[CatalogueStage],
    raw_picks: dict[str, list[str]],
    l3: list[StageCapabilities],
) -> None:
    """Reassign a mislinked L3 to its owning stage instead of losing it.

    A capability id is governed by exactly one stage, so an L3 the batched call put under the WRONG
    stage (dropped by _resolve) is added to its true owner's result (if not already there). The
    strict-isolation prompt should make this a no-op; it's the correction layer so a mislinked-but-
    valid capability is recovered, not lost. Salvaged caps carry an empty reason.
    """
    owner_of = {c.capability_id: s for s in active for c in s.capabilities}  # cap id -> owning stage
    by_stage = {sc.stage_id: sc for sc in l3}
    for picker_stage, picks in raw_picks.items():
        for cap_id in picks:
            owner = owner_of.get(cap_id)
            if owner is None or owner.stage_id == picker_stage:
                continue  # invalid id, or correctly placed
            target = by_stage.get(owner.stage_id)
            if target is None or any(c.capability_id == cap_id for c in target.capabilities):
                continue  # owner already has it
            cap = next(c for c in owner.capabilities if c.capability_id == cap_id)
            target.capabilities.append(
                Capability(capability_id=cap_id, name=cap.capability_name, reason=""))


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
