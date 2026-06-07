"""Ticket context resolution (TDD 5.2 / ticket B2).

Resolves the idea-card source for a ticket and consolidates it into one
section-tagged blob for the condense LLM pass. Both source paths (idea card vs
description + top-4 attachments) converge on the same :class:`ResolvedContext`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from teg.condense.attachment_ranker import select_attachments
from teg.condense.config import CondenseConfig
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


def _consolidate(
    description: str,
    documents: list[tuple[str, str]],
    *,
    doc_char_budget: int | None = None,
    min_doc_chars: int = 0,
) -> str:
    """Combine the description (always full - the one authoritative source) with docs.

    ``doc_char_budget=None`` -> include each doc in full (idea-card path). Otherwise the
    documents share the budget evenly (fallback path), and docs that extract to fewer
    than ``min_doc_chars`` are dropped as near-empty (image files without OCR).
    """
    docs = [(name, text) for name, text in documents if text and text.strip()]
    if min_doc_chars:
        docs = [(name, text) for name, text in docs if len(text.strip()) >= min_doc_chars]

    blocks: list[str] = []
    if description.strip():
        blocks.append(_section("DESCRIPTION", description))
    if docs:
        per_doc = (doc_char_budget // len(docs)) if doc_char_budget else None
        for name, text in docs:
            body = text.strip() if per_doc is None else text.strip()[:per_doc]
            if body:
                blocks.append(_section(f"DOCUMENT: {name}", body))
    return "\n\n".join(blocks)


async def resolve_from_ticket(
    ticket: JiraTicket,
    jira_client: JiraClient,
    extractor: AttachmentTextExtractor,
    *,
    config: CondenseConfig = CondenseConfig(),
) -> ResolvedContext:
    """Idea-card-first resolution. Idea card -> sole attachment (used in full); else top-N."""
    selection = select_attachments(
        ticket.attachments,
        max_fallback=config.max_attachments,
        max_bytes=config.max_attachment_bytes,
    )

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

    if primary_source == "idea_card":
        consolidated = _consolidate(ticket.description, documents)  # idea card in full
    else:
        consolidated = _consolidate(
            ticket.description,
            documents,
            doc_char_budget=config.doc_char_budget,
            min_doc_chars=config.min_doc_chars,
        )

    return ResolvedContext(
        ticket_id=ticket.ticket_id,
        ticket_title=ticket.title,
        description=ticket.description,
        primary_source=primary_source,
        attachments_used=[a.filename for a in chosen],
        consolidated_text=consolidated,
    )
