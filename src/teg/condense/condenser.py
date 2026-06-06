"""Condense step (TDD 5.1 / ticket B1).

One LLM pass over the resolved ticket context -> summaryFields + generationSignals,
mapped into a :class:`CondensedTicket`. Missing or absent signal categories become
empty lists - we never fabricate evidence.
"""

from __future__ import annotations

import json

from teg.condense.ticket_context import ResolvedContext
from teg.domain.condensed import (
    CondensedTicket,
    Evidence,
    GenerationSignals,
    SummaryFields,
)
from teg.integrations.llm_client import LLMClient
from teg.prompts.loader import load_prompt

# The consolidated context is capped before the LLM call to control tokens (TDD 3).
_INPUT_CHAR_LIMIT = 60_000

# domain attribute -> JSON key for the 18 generation signals.
_SIGNAL_KEYS: dict[str, str] = {
    "market_segments": "marketSegments",
    "funding_model_signals": "fundingModelSignals",
    "market_opportunity": "marketOpportunity",
    "business_solution_objectives": "businessSolutionObjectives",
    "value_proposition": "valueProposition",
    "estimated_benefits": "estimatedBenefits",
    "dependencies": "dependencies",
    "resources_needed": "resourcesNeeded",
    "digital_experience_signals": "digitalExperienceSignals",
    "product_availability_signals": "productAvailabilitySignals",
    "plan_signals": "planSignals",
    "network_signals": "networkSignals",
    "product_pairing_signals": "productPairingSignals",
    "business_rules": "businessRules",
    "operational_signals": "operationalSignals",
    "reporting_signals": "reportingSignals",
    "training_signals": "trainingSignals",
    "notes": "notes",
}


class CondenseError(RuntimeError):
    pass


async def condense(context: ResolvedContext, llm_client: LLMClient) -> CondensedTicket:
    if not context.consolidated_text.strip():
        raise CondenseError(f"No source text to condense for {context.ticket_id}")

    prompt = load_prompt("condense")
    system, user = prompt.render(
        ticket_id=context.ticket_id,
        consolidated_text=context.consolidated_text[:_INPUT_CHAR_LIMIT],
    )
    raw = await llm_client.complete(system=system, user=user)
    payload = _parse_json(raw, context.ticket_id)

    return CondensedTicket(
        ticket_id=context.ticket_id,
        ticket_title=context.ticket_title,
        primary_source=context.primary_source,
        attachments_used=list(context.attachments_used),
        summary_fields=_summary_fields(payload.get("summaryFields", {})),
        generation_signals=_generation_signals(payload.get("generationSignals", {})),
        description=context.description,
        raw_text=context.consolidated_text,
    )


def _parse_json(raw: str, ticket_id: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise CondenseError(f"No JSON object in condense response for {ticket_id}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise CondenseError(f"Invalid condense JSON for {ticket_id}: {exc}") from exc


def _summary_fields(data: dict) -> SummaryFields:
    return SummaryFields(
        generated_summary=str(data.get("generatedSummary", "")),
        business_problem=str(data.get("businessProblem", "")),
        business_capability=str(data.get("businessCapability", "")),
        key_terms=_str_list(data.get("keyTerms")),
        stakeholders=_str_list(data.get("stakeholders")),
        systems_and_products=_str_list(data.get("systemsAndProducts")),
    )


def _generation_signals(data: dict) -> GenerationSignals:
    return GenerationSignals(
        **{attr: _evidence_list(data.get(key)) for attr, key in _SIGNAL_KEYS.items()}
    )


def _evidence_list(items: object) -> list[Evidence]:
    if not isinstance(items, list):
        return []
    evidence: list[Evidence] = []
    for item in items:
        if isinstance(item, dict) and str(item.get("text", "")).strip():
            evidence.append(
                Evidence(
                    text=str(item["text"]),
                    source=str(item.get("source", "")),
                    source_section=(str(item["sourceSection"]) if item.get("sourceSection") else None),
                )
            )
    return evidence


def _str_list(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item) for item in items if str(item).strip()]
