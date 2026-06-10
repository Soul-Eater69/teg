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
from teg.theme.context import render_generation_signals, render_ticket_context
from teg.theme.stage_catalogue import render_candidate_stages

# Stage selection is about matching the idea-card ACTION to a stage; that lives in the
# summary fields. Most generation signals (plans, funding, networks, operational, reporting)
# are about availability/needs and add noise here - only the solution objectives (the
# concrete feature list) genuinely help map work to stages.
_STAGE_SIGNALS = ["businessSolutionObjectives"]


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
    active = [i for i in inputs if i.stages]  # a VS with no candidate stages has nothing to pick
    if not active:
        return {}

    prompt = load_prompt("theme/stage_selection")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        generation_signals=render_generation_signals(condensed, _STAGE_SIGNALS),
        value_streams="\n\n".join(_vs_block(i) for i in active),
    )
    result = await llm_client.complete(system=system, user=user, schema=BatchedStageSelection)

    by_vs = {r.value_stream_id: r for r in result.value_streams}
    return {
        i.value_stream.value_stream_id: _resolve(by_vs.get(i.value_stream.value_stream_id), i.stages)
        for i in active
    }


async def select_stages(
    *,
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    value_proposition: str,
    stages: list[CatalogueStage],
    llm_client: LLMClient,
) -> list[SelectedStage]:
    """Stages for a single value stream (wraps the batched call with one input)."""
    results = await select_stages_for_all(
        condensed=condensed,
        inputs=[StageSelectionInput(value_stream, value_stream_description, value_proposition, stages)],
        llm_client=llm_client,
    )
    return results.get(value_stream.value_stream_id, [])


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
