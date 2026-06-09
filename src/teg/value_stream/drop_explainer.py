"""Eval-only probe: why did the selector drop a candidate it actually saw?

Given the exact review-pool blocks the selection LLM read, the picks it made, and a set
of dropped candidate ids (the GT misses bucketed as ``llm_dropped``), ask the model to
classify each drop into a small fixed taxonomy. This runs AFTER scoring - it never feeds
back into the prediction or the metrics, so it can safely look at the dropped ids. It is a
post-hoc reason classifier over the same context, not the original call's chain of thought.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from teg.domain.base import CamelModel
from teg.integrations.llm import LLMClient
from teg.value_stream.candidate_blocks import render_candidate_blocks
from teg.value_stream.models import ValueStreamCandidate

DropReason = Literal[
    "off_topic",  # genuinely not relevant to this ticket
    "lower_priority",  # relevant, but less central than the picks (count-limited it out)
    "near_duplicate_of_pick",  # a sibling / near-twin was picked instead
    "thin_context",  # relevant, but this candidate's own block was too sparse to justify
    "other",
]

_SYSTEM = (
    "You are auditing a value-stream selection. A model was shown the candidate blocks below "
    "for a ticket and picked some of them. For each candidate id you are asked about (all of "
    "which were NOT picked), state the single most likely reason it was left out, using only "
    "these codes: off_topic (not relevant to the ticket), lower_priority (relevant but less "
    "central than the picks), near_duplicate_of_pick (a near-twin was picked instead), "
    "thin_context (relevant but its block was too sparse to justify), other. Add a short note. "
    "Judge only from the ticket and the blocks shown."
)


class DropExplanation(CamelModel):
    entity_id: str
    reason_code: DropReason = "other"
    note: str = ""


class DropExplanations(CamelModel):
    explanations: list[DropExplanation] = Field(default_factory=list)


async def explain_drops(
    *,
    query: str,
    review_pool: list[ValueStreamCandidate],
    picked_ids: list[str],
    dropped_ids: list[str],
    llm_client: LLMClient,
) -> dict[str, DropExplanation]:
    """Return {entity_id: explanation} for each dropped id the model can account for."""
    if not dropped_ids:
        return {}
    by_id = {c.value_stream_id: c for c in review_pool}
    picked = [by_id[i].value_stream_name for i in picked_ids if i in by_id]
    asked = [f"{i} ({by_id[i].value_stream_name})" for i in dropped_ids if i in by_id]
    if not asked:
        return {}

    user = (
        f"TICKET:\n{query}\n\n"
        f"PICKED: {', '.join(picked) or '(none)'}\n\n"
        f"CANDIDATE BLOCKS (what the selector saw):\n{render_candidate_blocks(review_pool)}\n\n"
        f"Explain why each of these was NOT picked:\n" + "\n".join(asked)
    )
    result = await llm_client.complete(system=_SYSTEM, user=user, schema=DropExplanations)
    return {e.entity_id: e for e in result.explanations}
