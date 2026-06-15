"""Eval-only probe: why did L3 selection drop a GT capability it saw?

Like stages, every candidate L3 for a stage is in the prompt, so a dropped GT L3 (one that IS in the
stage's candidate list - the answerable set) is always 'the model saw it and didn't pick it'. This
classifies each dropped answerable GT L3 by evidence, so we can tell a fixable miss from label noise:

  context_present_but_dropped : the idea card's work clearly exercises this capability - should have
                                been picked (the prompt-fixable miss)
  no_context_for_capability   : nothing in the card points to it - the BA tagged it by capability-
                                model convention (label noise - not derivable)
  weak_broad_context          : only indirect/partial evidence - borderline
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from teg.domain.base import CamelModel
from teg.ingestion.catalogues.models import CatalogueCapability
from teg.integrations.llm import LLMClient

L3Grounding = Literal[
    "context_present_but_dropped",
    "no_context_for_capability",
    "weak_broad_context",
    "other",
]


class L3GroundingExplanation(CamelModel):
    capability_id: str
    grounding: L3Grounding = "other"
    note: str = ""


class L3GroundingExplanations(CamelModel):
    explanations: list[L3GroundingExplanation] = Field(default_factory=list)


_SYSTEM = (
    "You audit L3 business-capability selection for ONE lifecycle stage. The idea card and the "
    "stage's candidate capabilities are shown. For each CORRECT-but-left-out capability, judge ONLY "
    "the evidence: does the idea card's work exercise that capability (run through / feed / change "
    "it)? Choose one code: context_present_but_dropped (the card's work clearly exercises it and it "
    "was shown - it should have been picked), no_context_for_capability (nothing in the card points "
    "to it - it was tagged by capability-model convention, not derivable from the card), "
    "weak_broad_context (only indirect/partial evidence - borderline), other. Add a one-line note."
)


def _render(caps: list[CatalogueCapability]) -> str:
    return "\n".join(
        f"- {c.capability_id} | {c.capability_name}"
        + (f" - {c.capability_description}" if c.capability_description else "")
        for c in caps)


async def classify_l3_drop_grounding(
    *,
    ticket_context: str,
    stage_name: str,
    candidates: list[CatalogueCapability],
    dropped_ids: list[str],
    llm_client: LLMClient,
) -> dict[str, L3GroundingExplanation]:
    """Per dropped GT L3: was the card evidence present (fixable) or absent (convention/noise)?"""
    if not dropped_ids:
        return {}
    by_id = {c.capability_id: c for c in candidates}
    asked = [f"{i} ({by_id[i].capability_name})" for i in dropped_ids if i in by_id]
    if not asked:
        return {}
    user = (
        f"IDEA CARD:\n{ticket_context}\n\n"
        f"STAGE: {stage_name}\n\n"
        f"CANDIDATE CAPABILITIES:\n{_render(candidates)}\n\n"
        f"For each left-out CORRECT capability, classify the evidence:\n" + "\n".join(asked)
    )
    result = await llm_client.complete(system=_SYSTEM, user=user, schema=L3GroundingExplanations)
    return {e.capability_id: e for e in result.explanations}


# --------------------------------------------------------------------------- #
# Pick relevance: are the model's PICKS that aren't in GT actually irrelevant, or plausible?
# --------------------------------------------------------------------------- #

L3PickVerdict = Literal[
    "relevant",    # the card's work exercises it - a plausible pick the GT just didn't tag
    "weak",        # only indirect/partial evidence - borderline
    "irrelevant",  # nothing in the card supports it - genuine over-pick / noise
    "other",
]


class L3PickExplanation(CamelModel):
    capability_id: str
    verdict: L3PickVerdict = "other"
    note: str = ""


class L3PickExplanations(CamelModel):
    explanations: list[L3PickExplanation] = Field(default_factory=list)


_PICK_SYSTEM = (
    "You audit L3 business-capability selection for ONE lifecycle stage. The idea card and the "
    "stage's candidate capabilities are shown. A model PICKED the capabilities listed below (none of "
    "which are in the ground-truth answer key). For EACH, judge ONLY the idea card's evidence: does "
    "the card's work actually exercise that capability (run through / feed / change it)? Choose one "
    "code: relevant (the card clearly exercises it - a plausible pick the answer key simply didn't "
    "tag), weak (only indirect/partial evidence - borderline), irrelevant (nothing in the card "
    "supports it - a genuine over-pick / noise), other. Add a one-line note."
)


async def classify_l3_pick_relevance(
    *,
    ticket_context: str,
    stage_name: str,
    candidates: list[CatalogueCapability],
    picked_ids: list[str],
    llm_client: LLMClient,
) -> dict[str, L3PickExplanation]:
    """Per picked-but-not-GT L3: is it relevant (GT under-tagged) or irrelevant (over-pick/noise)?"""
    if not picked_ids:
        return {}
    by_id = {c.capability_id: c for c in candidates}
    asked = [f"{i} ({by_id[i].capability_name})" for i in picked_ids if i in by_id]
    if not asked:
        return {}
    user = (
        f"IDEA CARD:\n{ticket_context}\n\n"
        f"STAGE: {stage_name}\n\n"
        f"CANDIDATE CAPABILITIES:\n{_render(candidates)}\n\n"
        f"For each PICKED (non-answer-key) capability, judge its relevance:\n" + "\n".join(asked)
    )
    result = await llm_client.complete(system=_PICK_SYSTEM, user=user, schema=L3PickExplanations)
    return {e.capability_id: e for e in result.explanations}
