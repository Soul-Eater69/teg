"""Stage selection for the approved value streams of one idea (batched).

One LLM call picks lifecycle stages for EVERY approved value stream at once - each value
stream from its own governed candidate stages (never invents or renames). Output is
BatchedStageSelection (structured output), keyed by valueStreamId; we resolve each value
stream's picks back to its canonical catalogue stages. Picks that don't resolve to that value
stream's allowed stages are dropped. ``select_stages`` wraps the batched call for one VS.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from teg.contracts.theme_io import ApprovedValueStream, CondensedContext, SelectedStage
from teg.domain.base import CamelModel
from teg.ingestion.catalogues.models import CatalogueStage
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.theme.context import render_ticket_context
from teg.theme.stage_catalogue import render_candidate_stages

# Stage selection is about matching the idea-card ACTION to a stage; that lives in the
# summary fields. Most generation signals (plans, funding, networks, operational, reporting)
# are about availability/needs and add noise here - only the solution objectives (the
# concrete feature list) genuinely help map work to stages.


class StageSelectionItem(CamelModel):
    stage_id: str
    stage_name: str = ""
    reason: str = ""


class VsStageSelection(CamelModel):
    """One value stream's stage selection (a batched-output entry).

    selectedStages = the stages the idea card's work belongs to (best guess, lean to include).
    Leave it empty to take the whole lifecycle - the full stage list is then used for the
    architect to trim. No scope flag: empty simply means "the full list".
    """

    value_stream_id: str
    selected_stages: list[StageSelectionItem] = Field(default_factory=list)


class BatchedStageSelection(CamelModel):
    """The selection LLM's structured output: one entry per approved value stream."""

    value_streams: list[VsStageSelection] = Field(default_factory=list)


class SingleStageSelection(CamelModel):
    """The single-value-stream selection LLM's structured output (the per_vs prompt)."""

    selected_stages: list[StageSelectionItem] = Field(default_factory=list)


@dataclass(frozen=True)
class StageSelectionInput:
    """One approved value stream and its governed candidate stages, for batched selection."""

    value_stream: ApprovedValueStream
    value_stream_description: str
    value_proposition: str
    stages: list[CatalogueStage]


async def select_stages_for_all(
    *,
    condensed: CondensedContext,
    inputs: list[StageSelectionInput],
    llm_client: LLMClient,
) -> dict[str, list[SelectedStage]]:
    """Pick stages for every approved value stream in one call. Returns {vs_id: stages}."""
    resolved, _ = await select_stages_for_all_traced(
        condensed=condensed, inputs=inputs, llm_client=llm_client
    )
    return resolved


async def select_stages_for_all_traced(
    *,
    condensed: CondensedContext,
    inputs: list[StageSelectionInput],
    llm_client: LLMClient,
) -> tuple[dict[str, list[SelectedStage]], dict[str, list[str]]]:
    """Same batched call, but also return the LLM's RAW picks per VS (unresolved).

    The second value is ``{vs_id: [picked stage_id, ...]}`` exactly as the LLM returned it,
    BEFORE :func:`_resolve` drops ids foreign to that VS - so eval can measure cross-VS
    mislinking (a stage the batched call put under the wrong value stream).
    """
    active = [i for i in inputs if i.stages]  # a VS with no candidate stages has nothing to pick
    if not active:
        return {}, {}

    prompt = load_prompt("theme/stage_selection")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        value_streams="\n\n".join(_vs_block(i) for i in active),
    )
    result = await llm_client.complete(system=system, user=user, schema=BatchedStageSelection)

    by_vs = {r.value_stream_id: r for r in result.value_streams}
    resolved: dict[str, list[SelectedStage]] = {}
    raw_picks: dict[str, list[str]] = {}
    for i in active:
        vs_id = i.value_stream.value_stream_id
        entry = by_vs.get(vs_id)
        resolved[vs_id] = _resolve(entry, i.stages)
        raw_picks[vs_id] = [item.stage_id for item in (entry.selected_stages if entry else [])]

    # Salvage cross-VS mislinks: a stage id is globally unique to one value stream, so a pick that
    # the model put under the WRONG value stream is reassigned to its true owner (if that VS is in
    # the batch and doesn't already have it). The prompt's strict isolation should make this a no-op;
    # this is the safety net so a mislinked-but-valid stage is recovered, not lost. Salvaged stages
    # carry an empty reason (they were not reasoned under their owner).
    _salvage_mislinks(active, raw_picks, resolved)
    return resolved, raw_picks


def _salvage_mislinks(
    active: list[StageSelectionInput],
    raw_picks: dict[str, list[str]],
    resolved: dict[str, list[SelectedStage]],
) -> None:
    owner_of = {s.stage_id: i for i in active for s in i.stages}  # stage id -> its owning input
    for picker_vs, picks in raw_picks.items():
        for stage_id in picks:
            owner = owner_of.get(stage_id)
            if owner is None or owner.value_stream.value_stream_id == picker_vs:
                continue  # invalid id, or correctly placed - nothing to salvage
            owner_vs = owner.value_stream.value_stream_id
            current = resolved.get(owner_vs, [])
            if any(s.stage_id == stage_id for s in current):
                continue  # the owner already has it
            stage = next(s for s in owner.stages if s.stage_id == stage_id)
            resolved[owner_vs] = current + [
                SelectedStage(stage_id=stage_id, stage_name=stage.stage_name, reason="")
            ]


async def select_stages(
    *,
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    value_proposition: str,
    stages: list[CatalogueStage],
    llm_client: LLMClient,
) -> list[SelectedStage]:
    """Stages for a SINGLE value stream via its own focused prompt (no cross-VS concern)."""
    if not stages:
        return []
    input_ = StageSelectionInput(value_stream, value_stream_description, value_proposition, stages)
    prompt = load_prompt("theme/stage_selection_single")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        value_stream=_vs_block(input_),
    )
    result = await llm_client.complete(system=system, user=user, schema=SingleStageSelection)
    return _resolve(VsStageSelection(value_stream_id=value_stream.value_stream_id,
                                     selected_stages=result.selected_stages), stages)


def _vs_block(i: StageSelectionInput) -> str:
    lines = [
        f"### Value stream {i.value_stream.value_stream_id}",
        f"Name: {i.value_stream.value_stream_name}",
    ]
    if i.value_stream_description:
        lines.append(f"Description: {i.value_stream_description}")
    if i.value_proposition:
        lines.append(f"Value proposition: {i.value_proposition}")
    lines.append("Candidate stages:")
    lines.append(render_candidate_stages(i.stages))
    return "\n".join(lines)


def _resolve(result: VsStageSelection | None, stages: list[CatalogueStage]) -> list[SelectedStage]:
    by_id = {s.stage_id: s for s in stages}
    all_stages = [(s.stage_id, "") for s in stages]  # whole lifecycle, for the architect to trim

    picks = [
        (item.stage_id, item.reason)
        for item in (result.selected_stages if result else [])
        if item.stage_id in by_id  # only this VS's governed stages; no invented/foreign ids
    ]
    # Never leave an approved VS empty: an empty / all-invalid pick takes the full stage list.
    chosen = picks or all_stages

    out: list[SelectedStage] = []
    seen: set[str] = set()
    for stage_id, reason in chosen:
        if stage_id in seen:
            continue
        seen.add(stage_id)
        out.append(
            SelectedStage(stage_id=stage_id, stage_name=by_id[stage_id].stage_name, reason=reason)
        )
    return out
