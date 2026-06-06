"""Ticket context resolution (TDD 5.2 / ticket B2).

Resolves the idea-card source for a ticket and consolidates it into one
section-tagged blob for the condense LLM pass. Both source paths (idea card vs
description + top-4 attachments) converge on the same :class:`ResolvedContext`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from teg.condense.attachment_ranker import select_attachments
from teg.integrations.jira_client import (
    AttachmentTextExtractor,
    JiraAttachment,
    JiraClient,
    JiraTicket,
)


@dataclass
class ResolvedContext:
    ticket_id: str
    ticket_title: str
    description: str
    primary_source: str  # "idea_card" | "attachments_fallback"
    attachments_used: list[str] = field(default_factory=list)
    consolidated_text: str = ""


def _section(tag: str, body: str) -> str:
    return f"[{tag}]\n{body.strip()}"


def _consolidate(description: str, documents: list[tuple[str, str]]) -> str:
    """Join the description and extracted documents into a tagged blob."""
    blocks: list[str] = []
    if description.strip():
        blocks.append(_section("DESCRIPTION", description))
    for filename, text in documents:
        if text.strip():
            blocks.append(_section(f"DOCUMENT: {filename}", text))
    return "\n\n".join(blocks)


async def resolve_from_ticket(
    ticket: JiraTicket,
    jira_client: JiraClient,
    extractor: AttachmentTextExtractor,
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
        content = await jira_client.download_attachment(ticket.ticket_id, attachment.filename)
        return attachment.filename, extractor.extract(attachment.filename, content)

    documents = list(await asyncio.gather(*(_extract(a) for a in chosen)))

    return ResolvedContext(
        ticket_id=ticket.ticket_id,
        ticket_title=ticket.title,
        description=ticket.description,
        primary_source=primary_source,
        attachments_used=[a.filename for a in chosen],
        consolidated_text=_consolidate(ticket.description, documents),
    )
