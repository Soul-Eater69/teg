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


def _section(tag: str, body: str) -> str:
    return f"[{tag}]\n{body.strip()}"


def _consolidate(description: str, documents: list[tuple[str, str]], doc_char_budget: int) -> str:
    """Description in full + an even share of the document budget per attachment.

    The description is the one authoritative source, so it is never truncated. The
    documents share ``doc_char_budget`` evenly: with idea-card-first that single doc
    gets the whole budget; in the heuristic fallback the docs share it. So attachment
    COUNT does not change total size - only how finely the doc budget is sliced -
    which lets us keep several candidates for coverage at no extra cost.
    """
    docs = [(name, text) for name, text in documents if text and text.strip()]

    blocks: list[str] = []
    if description.strip():
        blocks.append(_section("DESCRIPTION", description))
    if docs:
        per_doc = doc_char_budget // len(docs)
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
    doc_char_budget: int = 20_000,
    max_attachments: int = 4,
) -> ResolvedContext:
    """Idea-card-first resolution. Idea card -> sole attachment; else top-N."""
    selection = select_attachments(ticket.attachments, max_fallback=max_attachments)

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
        consolidated_text=_consolidate(ticket.description, documents, doc_char_budget),
    )
