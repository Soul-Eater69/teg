"""Theme generation service facade (Contract C).

The backend calls :meth:`ThemeService.generate` after the SME approves the VS set.
One theme package is produced per approved Value Stream via an async fan-out.
"""

from __future__ import annotations

import asyncio

from teg.contracts.theme_io import ThemeGenerationRequest, ThemeGenerationResponse


class ThemeService:
    def __init__(self, cosmos_client, llm_client) -> None:
        self._cosmos = cosmos_client  # governed stage / L2 / L3 catalogues
        self._llm = llm_client

    async def generate(self, request: ThemeGenerationRequest) -> ThemeGenerationResponse:
        """Generate one theme package per approved Value Stream, in parallel.

        Per-VS fan-out:
          stage prediction  ||  theme description
                 |                     (both off condensed context)
                 +--> business needs, L2, L3   (all wait on stage output, run parallel)
          theme title is deterministic: "<ticket title> - <value stream name>".

        TODO: implement via teg.theme.orchestrator (asyncio.gather, no LangGraph).
        Backlog: C2 (orchestration), C3 (stage), C4 (description), C5 (business needs),
        C6/C7 (L2/L3), C9 (assembly).
        """
        # await asyncio.gather(*(self._generate_one(vs, request) for vs in request.approved_value_streams))
        raise NotImplementedError

    async def _generate_one(self, approved_vs, request: ThemeGenerationRequest):
        """Single approved VS -> one ThemePackage. Stage||description, then fan-out."""
        raise NotImplementedError
