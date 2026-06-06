"""Condense service facade (Contract A).

The backend calls :meth:`CondenseService.condense`. Clients are injected so unit
tests pass fakes - no live Jira/LLM calls in tests.
"""

from __future__ import annotations

from teg.contracts.condense_io import CondenseRequest, CondenseResponse


class CondenseService:
    def __init__(self, jira_client, llm_client) -> None:
        self._jira = jira_client
        self._llm = llm_client

    async def condense(self, request: CondenseRequest) -> CondenseResponse:
        """Resolve the idea-card source, run the single condense pass, return it.

        Flow (TDD 5.1-5.2):
          1. ticket context: idea-card-first source resolution (PPT/PPTX -> PDF -> DOC, top 4).
          2. one LLM pass -> summaryFields + generationSignals (evidence; [] when absent).

        TODO: implement via teg.condense.ticket_context + teg.condense.condenser.
        Backlog: A7 (attachment priority), B1 (condense), B2 (ticket context).
        """
        raise NotImplementedError
