"""Business Needs generation for the selected stages of an approved Value Stream.

Runs after stage selection. One LLM call over all selected stages produces the final
consolidated Business Needs text (one draft, grouped by Value Stage -> Business Product
Feature -> needs, with Operational Training / Reporting where signals exist). Grounded in the
condensed context; no invention, no assumptions (deferred). Returns the text string.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import Field

from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.base import CamelModel
from teg.ingestion.catalogues.models import CatalogueStage
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.theme.context import render_generation_signals, render_ticket_context
from teg.theme.stage_catalogue import render_candidate_stages

# Generation signals fed to the business needs prompt (Contract C, section 5.1).
_BUSINESS_NEEDS_SIGNALS = [
    "businessSolutionObjectives",
    "dependencies",
    "resourcesNeeded",
    "digitalExperienceSignals",
    "businessRules",
    "operationalSignals",
    "reportingSignals",
    "trainingSignals",
    "notes",
]


class _GeneratedBusinessNeeds(CamelModel):
    """LLM structured output: the consolidated Business Needs text."""

    text: str


async def generate_business_needs(
    *,
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    value_proposition: str,
    selected_stages: list[CatalogueStage],
    llm_client: LLMClient,
) -> str:
    if not selected_stages:
        return ""
    prompt = load_prompt("theme/business_needs")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        generation_signals=render_generation_signals(condensed, _BUSINESS_NEEDS_SIGNALS),
        value_stream_id=value_stream.value_stream_id,
        value_stream_name=value_stream.value_stream_name,
        value_stream_description=value_stream_description,
        value_proposition=value_proposition,
        selected_stages=render_candidate_stages(selected_stages),
    )
    result = await llm_client.complete(system=system, user=user, schema=_GeneratedBusinessNeeds)
    return result.text


# --------------------------------------------------------------------------- #
# Batched: all value streams' Business Needs in ONE call (optimisation - fewer calls than per-VS).
# --------------------------------------------------------------------------- #

@dataclass
class BusinessNeedsInput:
    """One value stream's inputs for the batched call."""

    value_stream: ApprovedValueStream
    value_stream_description: str
    value_proposition: str
    selected_stages: list[CatalogueStage] = field(default_factory=list)


class _VsBusinessNeeds(CamelModel):
    value_stream_id: str
    text: str = ""


class _BatchedBusinessNeeds(CamelModel):
    """LLM structured output: one Business Needs document per value stream."""

    value_streams: list[_VsBusinessNeeds] = Field(default_factory=list)


def _vs_needs_block(i: BusinessNeedsInput) -> str:
    return (
        f"### Value stream {i.value_stream.value_stream_id}\n"
        f"Name: {i.value_stream.value_stream_name}\n"
        f"Description: {i.value_stream_description}\n"
        f"Value proposition: {i.value_proposition}\n"
        f"Selected stages (write needs for these only):\n"
        f"{render_candidate_stages(i.selected_stages)}"
    )


async def generate_business_needs_batched(
    *,
    condensed: CondensedContext,
    inputs: list[BusinessNeedsInput],
    llm_client: LLMClient,
) -> dict[str, str]:
    """One call for all value streams -> {value_stream_id: Business Needs text}. Empty VS omitted."""
    active = [i for i in inputs if i.selected_stages]
    if not active:
        return {}
    prompt = load_prompt("theme/business_needs_batched")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        generation_signals=render_generation_signals(condensed, _BUSINESS_NEEDS_SIGNALS),
        value_streams="\n\n".join(_vs_needs_block(i) for i in active),
    )
    result = await llm_client.complete(system=system, user=user, schema=_BatchedBusinessNeeds)
    by_id = {v.value_stream_id: v.text for v in result.value_streams}
    return {i.value_stream.value_stream_id: by_id.get(i.value_stream.value_stream_id, "")
            for i in active}
