"""Business Needs generation for the selected stages of an approved Value Stream.

Runs after stage selection. Stage-specific: one LLM call per selected stage (in parallel),
grouped by Business Product Feature, each need carrying optional Note / Dependency /
Business Rule. Operational Training and Reporting are included only when their signals exist.
Grounded in the condensed context; no invention, no assumptions (deferred).
"""

from __future__ import annotations

import asyncio

from pydantic import Field

from teg.contracts.theme_io import (
    ApprovedValueStream,
    BusinessNeed,
    BusinessProductFeature,
    CondensedContext,
)
from teg.domain.base import CamelModel
from teg.ingestion.catalogues.models import CatalogueStage
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.theme.context import render_generation_signals, render_ticket_context

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


class _GeneratedBusinessNeed(CamelModel):
    """LLM structured output for one selected stage (stage id/name added by us)."""

    business_product_features: list[BusinessProductFeature] = Field(default_factory=list)
    operational_training: list[str] = Field(default_factory=list)
    operational_reporting: list[str] = Field(default_factory=list)
    validation_status: str = "valid"


async def generate_business_needs(
    *,
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    selected_stages: list[CatalogueStage],
    llm_client: LLMClient,
) -> list[BusinessNeed]:
    return list(
        await asyncio.gather(
            *(
                _for_stage(condensed, value_stream, value_stream_description, stage, llm_client)
                for stage in selected_stages
            )
        )
    )


async def _for_stage(
    condensed: CondensedContext,
    value_stream: ApprovedValueStream,
    value_stream_description: str,
    stage: CatalogueStage,
    llm_client: LLMClient,
) -> BusinessNeed:
    prompt = load_prompt("theme/business_needs")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        generation_signals=render_generation_signals(condensed, _BUSINESS_NEEDS_SIGNALS),
        value_stream_id=value_stream.value_stream_id,
        value_stream_name=value_stream.value_stream_name,
        value_stream_description=value_stream_description,
        stage_id=stage.stage_id,
        stage_name=stage.stage_name,
        stage_description=stage.stage_description,
    )
    result = await llm_client.complete(system=system, user=user, schema=_GeneratedBusinessNeed)
    return BusinessNeed(
        stage_id=stage.stage_id,
        stage_name=stage.stage_name,
        business_product_features=result.business_product_features,
        operational_training=result.operational_training,
        operational_reporting=result.operational_reporting,
        validation_status=result.validation_status,
    )
