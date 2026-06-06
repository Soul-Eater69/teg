"""Attachment selection for the idea-card source (TDD 3, 5.2 / ticket A7).

Rules:
  - Prefer the idea card: an attachment named/tagged ``idea_card.ppt`` / ``idea_card.pptx``
    is the sole primary source when present.
  - Otherwise take the top four *supported* attachments in priority order:
    PowerPoint, then PDF, then Word. Original order is preserved within a format.
Unsupported formats are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

from teg.integrations.jira_client import JiraAttachment

# Lower number = higher priority. PPT first: SMEs confirmed it is the common idea-card format.
_FORMAT_PRIORITY: dict[str, int] = {
    ".ppt": 0,
    ".pptx": 0,
    ".pdf": 1,
    ".doc": 2,
    ".docx": 2,
}

_MAX_FALLBACK_ATTACHMENTS = 4
_IDEA_CARD_STEMS = ("idea_card", "ideacard", "idea card")


def _extension(filename: str) -> str:
    name = filename.lower().strip()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def is_supported(filename: str) -> bool:
    return _extension(filename) in _FORMAT_PRIORITY


def is_idea_card(filename: str) -> bool:
    """True for idea_card.ppt / idea_card.pptx (and close name variants)."""
    name = filename.lower().strip()
    if _extension(name) not in (".ppt", ".pptx"):
        return False
    stem = name[: name.rfind(".")]
    return any(token in stem for token in _IDEA_CARD_STEMS)


@dataclass
class SelectedAttachments:
    """What the condense source resolver should extract.

    When ``idea_card`` is set it is the sole primary source. Otherwise ``fallback``
    holds up to four supported attachments in priority order.
    """

    idea_card: JiraAttachment | None
    fallback: list[JiraAttachment]


def select_attachments(attachments: list[JiraAttachment]) -> SelectedAttachments:
    for attachment in attachments:
        if is_idea_card(attachment.filename):
            return SelectedAttachments(idea_card=attachment, fallback=[])

    supported = [a for a in attachments if is_supported(a.filename)]
    ranked = sorted(
        enumerate(supported),
        key=lambda pair: (_FORMAT_PRIORITY[_extension(pair[1].filename)], pair[0]),
    )
    fallback = [attachment for _, attachment in ranked[:_MAX_FALLBACK_ATTACHMENTS]]
    return SelectedAttachments(idea_card=None, fallback=fallback)
