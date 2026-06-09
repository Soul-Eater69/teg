"""Per-VS theme package assembly.

For one approved Value Stream: theme description and stage selection run in parallel off the
condensed context; business needs then run on the selected stages (they depend on the stage
output). L2/L3 capabilities are a later step. The theme title is deterministic:
"<ticket title> - <value stream name>".
"""

from __future__ import annotations

import asyncio

from teg.contracts.theme_io import ApprovedValueStream, ThemeGenerationRequest, ThemePackage
from teg.integrations.llm import LLMClient
from teg.theme.business_needs import generate_business_needs
from teg.theme.capabilities import generate_capabilities
from teg.theme.description import generate_theme_description
from teg.theme.stage_catalogue import StageCatalogue
from teg.theme.stage_selection import select_stages


async def generate_theme_package(
    *,
    approved_vs: ApprovedValueStream,
    request: ThemeGenerationRequest,
    stage_catalogue: StageCatalogue,
    llm_client: LLMClient,
) -> ThemePackage:
    stages = stage_catalogue.stages_for(approved_vs.value_stream_id)
    vs_description = stage_catalogue.description_for(approved_vs.value_stream_id)
    vs_proposition = stage_catalogue.value_proposition_for(approved_vs.value_stream_id)

    description, selected_stages = await asyncio.gather(
        generate_theme_description(
            condensed=request.condensed,
            value_stream_id=approved_vs.value_stream_id,
            value_stream_name=approved_vs.value_stream_name,
            value_stream_description=vs_description,
            value_proposition=vs_proposition,
            llm_client=llm_client,
        ),
        select_stages(
            condensed=request.condensed,
            value_stream=approved_vs,
            value_stream_description=vs_description,
            value_proposition=vs_proposition,
            stages=stages,
            llm_client=llm_client,
        ),
    )

    # Business needs and L3/L2 capabilities both depend on the selected stages and run in
    # parallel. Resolve the selected stages back to their full catalogue stage first.
    by_id = {s.stage_id: s for s in stages}
    selected_catalogue_stages = [by_id[s.stage_id] for s in selected_stages if s.stage_id in by_id]
    business_needs, (l3_capabilities, l2_capabilities) = await asyncio.gather(
        generate_business_needs(
            condensed=request.condensed,
            value_stream=approved_vs,
            value_stream_description=vs_description,
            value_proposition=vs_proposition,
            selected_stages=selected_catalogue_stages,
            llm_client=llm_client,
        ),
        generate_capabilities(
            condensed=request.condensed,
            value_stream=approved_vs,
            value_stream_description=vs_description,
            selected_stages=selected_catalogue_stages,
            llm_client=llm_client,
        ),
    )

    return ThemePackage(
        value_stream_id=approved_vs.value_stream_id,
        value_stream_name=approved_vs.value_stream_name,
        theme_title=f"{request.ticket_title} - {approved_vs.value_stream_name}",
        theme_description=description,
        selected_stages=selected_stages,
        business_needs=business_needs,
        l3_capabilities=l3_capabilities,
        l2_capabilities=l2_capabilities,
    )
