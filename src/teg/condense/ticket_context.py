"""Ticket context resolution (TDD 5.2 / ticket B2).

Resolves the idea-card source for a ticket and consolidates it into one
section-tagged blob for the condense LLM pass. Both source paths (idea card vs
description + top-4 attachments) converge on the same :class:`ResolvedContext`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from teg.condense.attachment_ranker import select_attachments
from teg.integrations.files import AttachmentTextExtractor
from teg.integrations.jira import JiraAttachment, JiraClient, JiraTicket


@dataclass
class ResolvedContext:
    ticket_id: str
    ticket_title: str
    description: str
    primary_source: str  # "idea_card" | "attachments_fallback"
    attachments_used: list[str] = field(default_factory=list)
    consolidated_text: str = ""


# Description gets first claim of the budget; documents share the rest.
_DESCRIPTION_BUDGET_FRACTION = 0.3


def _section(tag: str, body: str) -> str:
    return f"[{tag}]\n{body.strip()}"


def _consolidate(description: str, documents: list[tuple[str, str]], char_budget: int) -> str:
    """Combine description + documents within a total character budget.

    Description gets first claim (capped to a reserve when documents are present);
    the remaining budget is split evenly across documents. Since the top-4 fallback
    selection is heuristic, taking a bounded slice from each doc gives coverage of
    every candidate instead of betting the whole budget on the first one.
    """
    docs = [(name, text) for name, text in documents if text and text.strip()]
    description = description.strip()

    desc_budget = char_budget if not docs else int(char_budget * _DESCRIPTION_BUDGET_FRACTION)
    description = description[:desc_budget]
    per_doc = max(0, (char_budget - len(description)) // len(docs)) if docs else 0

    blocks: list[str] = []
    if description:
        blocks.append(_section("DESCRIPTION", description))
    for name, text in docs:
        chunk = text.strip()[:per_doc]
        if chunk:
            blocks.append(_section(f"DOCUMENT: {name}", chunk))
    return "\n\n".join(blocks)


async def resolve_from_ticket(
    ticket: JiraTicket,
    jira_client: JiraClient,
    extractor: AttachmentTextExtractor,
    *,
    char_budget: int = 24_000,
) -> ResolvedContext:
    """Idea-card-first resolution. Idea card -> sole attachment; else top-4."""
    selection = select_attachments(ticket.attachments)

    chosen: list[JiraAttachment]
    if selection.idea_card is not None:
        chosen = [selection.idea_card]
        primary_source = "idea_card"
    else:
        chosen = selection.fallback
        primary_source = "attachments_fallback"

    async def _extract(attachment: JiraAttachment) -> tuple[str, str]:
        content = await jira_client.download_attachment(attachment)
        return attachment.filename, extractor.extract(attachment.filename, content)

    documents = list(await asyncio.gather(*(_extract(a) for a in chosen)))

    return ResolvedContext(
        ticket_id=ticket.ticket_id,
        ticket_title=ticket.title,
        description=ticket.description,
        primary_source=primary_source,
        attachments_used=[a.filename for a in chosen],
        consolidated_text=_consolidate(ticket.description, documents, char_budget),
    )
