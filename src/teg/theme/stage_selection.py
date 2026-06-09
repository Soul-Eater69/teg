"""Stage selection for an already-selected Value Stream.

The LLM picks lifecycle stages from the VS's governed candidate stages (never invents or
renames). Output is StageSelectionResult (structured output); we then resolve each pick
back to the canonical catalogue stage and map to the contract's SelectedStage. Picks
that don't resolve to an allowed stage are dropped (no invented stages).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from teg.contracts.theme_io import ApprovedValueStream, CondensedContext, SelectedStage
from teg.domain.base import CamelModel
from teg.ingestion.catalogues.models import CatalogueStage
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.theme.context import render_generation_signals, render_ticket_context
from teg.theme.stage_catalogue import render_candidate_stages

StageScope = Literal["specific_stages", "entire_value_stream", "broad_or_unclear"]

# Stage selection is about matching the idea-card ACTION to a stage; that lives in the
# summary fields. Most generation signals (plans, funding, networks, operational, reporting)
# are about availability/needs and add noise here - only the solution objectives (the
# concrete feature list) genuinely help map work to stages.
_STAGE_SIGNALS = ["businessSolutionObjectives"]


class StageSelectionItem(CamelModel):
    stage_id: str
    stage_name: str = ""
    reason: str = ""


class StageSelectionResult(CamelModel):
    """The selection LLM's structured output."""

    stage_scope: StageScope = "broad_or_unclear"
    selected_stages: list[StageSelectionItem] = Field(default_factory=list)
    reason: str = ""


async def select_stages(
    *,
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    stages: list[CatalogueStage],
    llm_client: LLMClient,
) -> list[SelectedStage]:
    if not stages:
        return []
    prompt = load_prompt("theme/stage_selection")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        generation_signals=render_generation_signals(condensed, _STAGE_SIGNALS),
        value_stream_id=value_stream.value_stream_id,
        value_stream_name=value_stream.value_stream_name,
        value_stream_description=value_stream_description,
        candidate_stages=render_candidate_stages(stages),
    )
    result = await llm_client.complete(system=system, user=user, schema=StageSelectionResult)
    return _resolve(result, stages)


def _resolve(result: StageSelectionResult, stages: list[CatalogueStage]) -> list[SelectedStage]:
    by_id = {s.stage_id: s for s in stages}

    if result.stage_scope == "entire_value_stream":
        chosen = [(s.stage_id, "") for s in stages]  # the whole lifecycle
    elif result.stage_scope == "specific_stages":
        chosen = [
            (item.stage_id, item.reason)
            for item in result.selected_stages
            if item.stage_id in by_id  # only governed stages; no invented ids
        ]
    else:
        chosen = []  # broad_or_unclear -> no specific stages

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
