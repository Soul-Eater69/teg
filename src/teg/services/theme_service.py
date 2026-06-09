"""Theme generation service facade (Contract C).

The backend calls :meth:`ThemeService.generate` after the SME approves the VS set. One
theme package is produced per approved Value Stream via an async fan-out; within each, the
theme description and stage selection run in parallel. The governed stage catalogue is
injected (from the Sightline catalogue today; from Cosmos once that read exists).
"""

from __future__ import annotations

import asyncio

from teg.contracts.theme_io import ThemeGenerationRequest, ThemeGenerationResponse
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
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
        packages = await asyncio.gather(
            *(
                generate_theme_package(
                    approved_vs=vs,
                    request=request,
                    stage_catalogue=self._catalogue,
                    llm_client=self._llm,
                )
                for vs in request.approved_value_streams
            )
        )
        return ThemeGenerationResponse(
            ticket_id=request.ticket_id,
            theme_packages=list(packages),
            model=self._model_name,
            prompt_version=load_prompt("theme/description").version,
        )
