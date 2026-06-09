"""Business Needs generation for the selected stages of an approved Value Stream.

Runs after stage selection. One LLM call over all selected stages produces the final
consolidated Business Needs text (one draft, grouped by Value Stage -> Business Product
Feature -> needs, with Operational Training / Reporting where signals exist). Grounded in the
condensed context; no invention, no assumptions (deferred). Returns the text string.
"""

from __future__ import annotations

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
