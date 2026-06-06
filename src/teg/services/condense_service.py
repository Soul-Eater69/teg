"""Condense service facade (Contract A).

The backend calls :meth:`CondenseService.condense`. Clients are injected so unit
tests pass fakes - no live Jira/LLM calls in tests.
"""

from __future__ import annotations

from teg.condense.condenser import condense as run_condense
from teg.condense.ticket_context import resolve_from_ticket
from teg.contracts.condense_io import CondenseRequest, CondenseResponse
from teg.integrations.files import AttachmentTextExtractor
from teg.integrations.jira import JiraClient
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt


class CondenseService:
    def __init__(
        self,
        jira_client: JiraClient,
        llm_client: LLMClient,
        extractor: AttachmentTextExtractor,
        *,
        model_name: str = "",
    ) -> None:
        self._jira = jira_client
        self._llm = llm_client
        self._extractor = extractor
        self._model_name = model_name

    async def condense(self, request: CondenseRequest) -> CondenseResponse:
        """Fetch the ticket, resolve the idea-card source, run the condense pass.

        Backlog: A7 (attachment priority), B1 (condense), B2 (ticket context).
        """
        ticket = await self._jira.fetch_ticket(request.ticket_id)
        context = await resolve_from_ticket(ticket, self._jira, self._extractor)
        condensed = await run_condense(context, self._llm)
        return CondenseResponse(
            condensed=condensed,
            model=self._model_name,
            prompt_version=load_prompt("condense/condense").version,
        )
