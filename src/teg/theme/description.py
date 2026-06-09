"""Theme Description generation for one approved Value Stream.

The LLM writes the description prose; Product Availability is organised strictly from the
provided generation signals (never invented). Output is the ThemeDescription (the
contract model used as the structured-output schema).
"""

from __future__ import annotations

from teg.contracts.theme_io import CondensedContext, ThemeDescription
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.theme.context import render_generation_signals, render_ticket_context

# Generation signals fed to the theme description prompt (Contract C, section 4.1).
_DESCRIPTION_SIGNALS = [
    "marketSegments",
    "fundingModelSignals",
    "marketOpportunity",
    "businessSolutionObjectives",
    "valueProposition",
    "estimatedBenefits",
    "dependencies",
    "resourcesNeeded",
    "digitalExperienceSignals",
    "productAvailabilitySignals",
    "planSignals",
    "networkSignals",
    "productPairingSignals",
    "operationalSignals",
    "reportingSignals",
    "notes",
]


async def generate_theme_description(
    *,
    condensed: CondensedContext,
    value_stream_id: str,
    value_stream_name: str,
    value_stream_description: str,
    llm_client: LLMClient,
) -> ThemeDescription:
    prompt = load_prompt("theme/description")
    system, user = prompt.render(
        value_stream_id=value_stream_id,
        value_stream_name=value_stream_name,
        value_stream_description=value_stream_description,
        ticket_context=render_ticket_context(condensed),
        generation_signals=render_generation_signals(condensed, _DESCRIPTION_SIGNALS),
    )
    return await llm_client.complete(system=system, user=user, schema=ThemeDescription)
