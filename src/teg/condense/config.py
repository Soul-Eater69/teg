"""Condense tuning knobs.

Grouped so the service / resolution signatures stay small. The idea-card path
ignores all of these (the idea card is trusted and used in full); they govern only
the heuristic fallback (no idea card -> top-N attachments).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CondenseConfig:
    doc_char_budget: int = 40_000  # total chars across fallback docs, split per doc (~10k each at 4 docs)
    max_attachments: int = 4  # top-N fallback when no idea card
    max_attachment_bytes: int = 10_000_000  # skip larger fallback files pre-download (0 = off)
    min_doc_chars: int = 200  # drop fallback docs that extract to less than this
