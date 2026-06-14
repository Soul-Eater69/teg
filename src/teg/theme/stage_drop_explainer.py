"""Eval-only probes: why did stage selection drop a GT stage it actually saw?

Unlike VS prediction there is NO retrieval gate - every catalogue stage for a value stream is
printed in the prompt - so a dropped GT stage is always 'the LLM saw it and didn't pick it'. These
post-hoc probes (run AFTER scoring, never feeding back into metrics) classify each dropped GT stage:

  grounding : was the evidence for the stage present (fixable) or absent (justified / GT noise)?
  swap      : why did the picked stage(s) win over this dropped GT stage?

Both judge one value stream at a time, from its own candidate stages + the idea card.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from teg.domain.base import CamelModel
from teg.ingestion.catalogues.models import CatalogueStage
from teg.integrations.llm import LLMClient
from teg.theme.stage_catalogue import render_candidate_stages

StageGrounding = Literal[
    "context_present_but_dropped",  # the idea card supports this stage and it was shown - fixable
    "no_context_for_stage",  # nothing in the idea card points to this stage - drop justified (GT noise)
    "weak_broad_context",  # only indirect/partial evidence - borderline
    "other",
]

_GROUND_SYSTEM = (
    "You audit lifecycle-stage selection for ONE value stream. The candidate stages and the idea "
    "card are shown. For each CORRECT-but-left-out stage, judge ONLY the evidence: does the idea "
    "card's work fall within that stage's scope (its description / entrance-exit criteria)? Choose "
    "one code: context_present_but_dropped (the card's work clearly falls in this stage and it was "
    "shown - it should have been picked), no_context_for_stage (nothing in the card points to this "
    "stage - leaving it out was justified), weak_broad_context (only indirect/partial evidence - "
    "borderline), other. Add a one-line note citing the idea-card evidence or its absence."
)


class StageGroundingExplanation(CamelModel):
    stage_id: str
    grounding: StageGrounding = "other"
    note: str = ""


class StageGroundingExplanations(CamelModel):
    explanations: list[StageGroundingExplanation] = Field(default_factory=list)


async def classify_stage_drop_grounding(
    *,
    ticket_context: str,
    value_stream_name: str,
    stages: list[CatalogueStage],
    dropped_ids: list[str],
    llm_client: LLMClient,
) -> dict[str, StageGroundingExplanation]:
    """Per dropped GT stage: was its evidence present (fixable) or absent (justified)?"""
    if not dropped_ids:
        return {}
    by_id = {s.stage_id: s for s in stages}
    asked = [f"{i} ({by_id[i].stage_name})" for i in dropped_ids if i in by_id]
    if not asked:
        return {}
    user = (
        f"IDEA CARD:\n{ticket_context}\n\n"
        f"VALUE STREAM: {value_stream_name}\n\n"
        f"CANDIDATE STAGES:\n{render_candidate_stages(stages)}\n\n"
        f"For each left-out CORRECT stage, classify the evidence:\n" + "\n".join(asked)
    )
    result = await llm_client.complete(
        system=_GROUND_SYSTEM, user=user, schema=StageGroundingExplanations)
    return {e.stage_id: e for e in result.explanations}


StageSwapReason = Literal[
    "picks_more_specific",  # the picked stage matches the card's action more precisely
    "dropped_too_broad",  # the dropped stage is broader/adjacent, only loosely implied
    "no_evidence_for_dropped",  # nothing in the card points to the dropped stage
    "adjacent_stage_confusion",  # a neighbouring lifecycle stage was picked instead
    "dropped_is_valid_should_have_picked",  # on reflection the dropped stage was as applicable
    "other",
]

_SWAP_SYSTEM = (
    "You audit lifecycle-stage selection for ONE value stream. The model picked some stages and "
    "left out one that was correct (ground truth). Explain, grounded in the idea card, why the "
    "picks won over the left-out stage. Choose the best code: picks_more_specific (picks match the "
    "card's action more precisely), dropped_too_broad (the left-out stage is broader/adjacent, only "
    "loosely implied), no_evidence_for_dropped (nothing in the card points to it), "
    "adjacent_stage_confusion (a neighbouring stage was picked instead), "
    "dropped_is_valid_should_have_picked (it was genuinely as applicable - a real miss), other. "
    "Add a one-line note citing the card."
)


class StageSwapExplanation(CamelModel):
    dropped_id: str
    reason_code: StageSwapReason = "other"
    note: str = ""


class StageSwapExplanations(CamelModel):
    explanations: list[StageSwapExplanation] = Field(default_factory=list)


async def explain_stage_swaps(
    *,
    ticket_context: str,
    value_stream_name: str,
    stages: list[CatalogueStage],
    picked_ids: list[str],
    dropped_ids: list[str],
    llm_client: LLMClient,
) -> dict[str, StageSwapExplanation]:
    """Comparative: for each dropped GT stage, why the picked stage(s) beat it."""
    if not dropped_ids:
        return {}
    by_id = {s.stage_id: s for s in stages}
    picked = [by_id[i].stage_name for i in picked_ids if i in by_id]
    asked = [f"{i} ({by_id[i].stage_name})" for i in dropped_ids if i in by_id]
    if not asked or not picked:
        return {}
    user = (
        f"IDEA CARD:\n{ticket_context}\n\n"
        f"VALUE STREAM: {value_stream_name}\n\n"
        f"PICKED stages: {', '.join(picked)}\n\n"
        f"CANDIDATE STAGES:\n{render_candidate_stages(stages)}\n\n"
        f"For each CORRECT-but-left-out stage, explain why the picks beat it:\n" + "\n".join(asked)
    )
    result = await llm_client.complete(
        system=_SWAP_SYSTEM, user=user, schema=StageSwapExplanations)
    return {e.dropped_id: e for e in result.explanations}
