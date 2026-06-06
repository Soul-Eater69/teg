"""Condense service facade (Contract A).

The backend calls :meth:`CondenseService.condense`. Clients are injected so unit
tests pass fakes - no live Jira/LLM calls in tests.
"""

from __future__ import annotations

from dataclasses import fields

from teg.condense.condenser import condense as run_condense
from teg.condense.ticket_context import resolve_from_text, resolve_from_ticket
from teg.contracts.condense_io import (
    CondensedTicketDTO,
    CondenseRequest,
    CondenseResponse,
    EvidenceDTO,
    GenerationSignalsDTO,
    SummaryFieldsDTO,
)
from teg.domain.condensed import CondensedTicket, GenerationSignals, SummaryFields
from teg.integrations.jira_client import AttachmentTextExtractor, JiraClient
from teg.integrations.llm_client import LLMClient
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
        """Resolve the idea-card source (idea-card-first), run the condense pass.

        Backlog: A7 (attachment priority), B1 (condense), B2 (ticket context).
        """
        if request.idea_card_text:
            context = resolve_from_text(request.ticket_id or "", request.idea_card_text)
        elif request.ticket_id:
            ticket = await self._jira.fetch_ticket(request.ticket_id)
            context = await resolve_from_ticket(ticket, self._jira, self._extractor)
        else:
            raise ValueError("CondenseRequest needs ticket_id or idea_card_text")

        condensed = await run_condense(context, self._llm)
        return CondenseResponse(
            condensed=_to_dto(condensed),
            model=self._model_name,
            prompt_version=load_prompt("condense").version,
        )


def _to_dto(condensed: CondensedTicket) -> CondensedTicketDTO:
    return CondensedTicketDTO(
        ticket_id=condensed.ticket_id,
        ticket_title=condensed.ticket_title,
        primary_source=condensed.primary_source,
        attachments_used=condensed.attachments_used,
        summary_fields=_summary_dto(condensed.summary_fields),
        generation_signals=_signals_dto(condensed.generation_signals),
        description=condensed.normalized_context.description,
        raw_text=condensed.normalized_context.raw_text,
    )


def _summary_dto(summary: SummaryFields) -> SummaryFieldsDTO:
    return SummaryFieldsDTO(
        generated_summary=summary.generated_summary,
        business_problem=summary.business_problem,
        business_capability=summary.business_capability,
        key_terms=summary.key_terms,
        stakeholders=summary.stakeholders,
        systems_and_products=summary.systems_and_products,
    )


def _signals_dto(signals: GenerationSignals) -> GenerationSignalsDTO:
    return GenerationSignalsDTO(
        **{
            f.name: [
                EvidenceDTO(text=e.text, source=e.source, source_section=e.source_section)
                for e in getattr(signals, f.name)
            ]
            for f in fields(signals)
        }
    )
