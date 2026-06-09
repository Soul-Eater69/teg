"""Value Stream selection: the review-pool LLM call that picks the final streams.

Runs the (eval-winning) selection prompt over the rendered candidate blocks, then
resolves each pick back to its catalogue candidate, scales confidence to 0-100,
dedupes, and enforces the requested count.
"""

from __future__ import annotations

from pydantic import Field

from teg.domain.base import CamelModel
from teg.domain.value_stream import SupportType, ValueStreamRecommendation
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.value_stream.candidate_blocks import render_candidate_blocks
from teg.value_stream.models import ValueStreamCandidate

_FILL_CONFIDENCE = 30.0  # the 0.30 floor (as a percent) for count-fill picks


class ValueStreamPick(CamelModel):
    """One LLM pick. confidence is 0-1 as emitted by the model."""

    entity_id: str
    confidence: float = 0.0
    support_type: SupportType = "implied"
    reason: str = ""


class ValueStreamSelection(CamelModel):
    """The selection LLM's structured output."""

    picks: list[ValueStreamPick] = Field(default_factory=list)


async def select_value_streams(
    *,
    query: str,
    candidates: list[ValueStreamCandidate],
    requested_count: int,
    llm_client: LLMClient,
) -> list[ValueStreamRecommendation]:
    prompt = load_prompt("value_stream/selection")
    system, user = prompt.render(
        max_select=requested_count,
        requested_final_output_count=requested_count,
        query_for_prompt=query,
        candidate_blocks=render_candidate_blocks(candidates),
    )
    selection = await llm_client.complete(system=system, user=user, schema=ValueStreamSelection)
    recommendations = _resolve(selection, candidates)
    return _enforce_count(recommendations, candidates, requested_count)


def _resolve(
    selection: ValueStreamSelection, candidates: list[ValueStreamCandidate]
) -> list[ValueStreamRecommendation]:
    by_id = {c.value_stream_id: c for c in candidates}
    out: list[ValueStreamRecommendation] = []
    seen: set[str] = set()
    for pick in selection.picks:
        candidate = by_id.get(pick.entity_id)
        if candidate is None or candidate.value_stream_id in seen:
            continue  # only catalogue entity_ids, deduped
        seen.add(candidate.value_stream_id)
        confidence = min(max(pick.confidence, 0.0), 1.0) * 100
        out.append(_recommend(candidate, confidence, pick.support_type, pick.reason))
    return out


def _enforce_count(
    recommendations: list[ValueStreamRecommendation],
    candidates: list[ValueStreamCandidate],
    requested_count: int,
) -> list[ValueStreamRecommendation]:
    # Exact count: trim extras, or fill from the ranked pool at the confidence floor.
    if len(recommendations) >= requested_count:
        return recommendations[:requested_count]
    chosen = {r.value_stream_id for r in recommendations}
    for candidate in candidates:
        if len(recommendations) >= requested_count:
            break
        if candidate.value_stream_id in chosen:
            continue
        recommendations.append(_recommend(candidate, _FILL_CONFIDENCE, "implied", ""))
        chosen.add(candidate.value_stream_id)
    return recommendations


def _recommend(
    candidate: ValueStreamCandidate,
    confidence: float,
    support_type: SupportType,
    reason: str,
) -> ValueStreamRecommendation:
    return ValueStreamRecommendation(
        value_stream_id=candidate.value_stream_id,
        value_stream_name=candidate.value_stream_name,
        confidence=round(confidence, 1),
        support_type=support_type,
        reason=reason,
        # Source tickets are the historic analogs that justify an INFERRED pick, so they
        # are surfaced only for implied picks. A direct pick is explicitly named by the
        # idea card and needs no historic backing. (semantic_only picks have none anyway.)
        source_tickets=candidate.source_ticket_ids if support_type == "implied" else [],
    )
