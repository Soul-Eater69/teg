"""Theme generation service facade (Contract C).

The backend calls :meth:`ThemeService.generate` after the SME approves the VS set. The theme
description is generated ONCE per ticket - a shared VS-agnostic body plus a single batched call
for every value stream's framing paragraph - instead of a full description call per VS. Each
theme's description is framing + body. The rest (stage selection, business needs, capabilities)
fans out per approved Value Stream. The governed stage catalogue is injected (Sightline today;
Cosmos once that read exists).
"""

from __future__ import annotations

import asyncio

from teg.contracts.theme_io import ThemeGenerationRequest, ThemeGenerationResponse
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.theme.description import (
    assemble_description,
    generate_description_body,
    generate_vs_framings,
)
from teg.theme.orchestrator import generate_theme_package
from teg.theme.stage_catalogue import StageCatalogue


class ThemeService:
    def __init__(
        self,
        stage_catalogue: StageCatalogue,
        llm_client: LLMClient,
        *,
        model_name: str = "",
    ) -> None:
        self._catalogue = stage_catalogue
        self._llm = llm_client
        self._model_name = model_name

    async def generate(self, request: ThemeGenerationRequest) -> ThemeGenerationResponse:
        approved = request.approved_value_streams
        vs_details = {
            vs.value_stream_id: (
                self._catalogue.description_for(vs.value_stream_id),
                self._catalogue.value_proposition_for(vs.value_stream_id),
            )
            for vs in approved
        }
        # Description: one shared body + one batched call for every VS framing (2 calls total).
        body, framings = await asyncio.gather(
            generate_description_body(condensed=request.condensed, llm_client=self._llm),
            generate_vs_framings(
                condensed=request.condensed,
                approved_value_streams=approved,
                value_stream_details=vs_details,
                llm_client=self._llm,
            ),
        )

        packages = await asyncio.gather(
            *(
                generate_theme_package(
                    approved_vs=vs,
                    request=request,
                    stage_catalogue=self._catalogue,
                    llm_client=self._llm,
                    theme_description=assemble_description(
                        framings.get(vs.value_stream_id, ""), body
                    ),
                )
                for vs in approved
            )
        )
        return ThemeGenerationResponse(
            ticket_id=request.ticket_id,
            theme_packages=list(packages),
            model=self._model_name,
            prompt_version=load_prompt("theme/description_body").version,
        )
