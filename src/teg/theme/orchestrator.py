"""Per-VS theme package assembly.

For one approved Value Stream, the theme description and the stage selection are
independent - they run in parallel off the condensed context. Business needs and L2/L3
capabilities (which depend on the selected stages) are a later step. The theme title is
deterministic: "<ticket title> - <value stream name>".
"""

from __future__ import annotations

import asyncio

from teg.contracts.theme_io import ApprovedValueStream, ThemeGenerationRequest, ThemePackage
from teg.integrations.llm import LLMClient
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

    description, selected_stages = await asyncio.gather(
        generate_theme_description(
            condensed=request.condensed,
            value_stream_id=approved_vs.value_stream_id,
            value_stream_name=approved_vs.value_stream_name,
            value_stream_description=vs_description,
            llm_client=llm_client,
        ),
        select_stages(
            condensed=request.condensed,
            value_stream=approved_vs,
            value_stream_description=vs_description,
            stages=stages,
            llm_client=llm_client,
        ),
    )

    return ThemePackage(
        value_stream_id=approved_vs.value_stream_id,
        value_stream_name=approved_vs.value_stream_name,
        theme_title=f"{request.ticket_title} - {approved_vs.value_stream_name}",
        theme_description=description,
        selected_stages=selected_stages,
        # business_needs + l2/l3 capabilities depend on selected_stages - next step.
    )
