"""Condense step (TDD 5.1 / ticket B1).

One structured LLM pass over the resolved ticket context -> summaryFields +
generationSignals, assembled into a :class:`CondensedTicket`. The output shape is the
:class:`CondenseExtraction` pydantic schema (provider-enforced), so there is no
hand-parsing here and absent signal categories default to empty lists.
"""

from __future__ import annotations

from teg.condense.ticket_context import ResolvedContext
from teg.domain.condensed import CondensedTicket, CondenseExtraction
from teg.integrations.llm_client import LLMClient
from teg.prompts.loader import load_prompt

# The consolidated context is capped before the LLM call to control tokens (TDD 3).
_INPUT_CHAR_LIMIT = 60_000


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
    extraction = await llm_client.complete(system=system, user=user, schema=CondenseExtraction)

    return CondensedTicket(
        ticket_id=context.ticket_id,
        ticket_title=context.ticket_title,
        primary_source=context.primary_source,
        attachments_used=list(context.attachments_used),
        summary_fields=extraction.summary_fields,
        generation_signals=extraction.generation_signals,
        description=context.description,
        raw_text=context.consolidated_text,
    )
