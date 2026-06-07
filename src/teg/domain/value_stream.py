"""Value Stream prediction records (TDD 5.3-5.5).

Single source of truth for the VS output shapes - used internally and serialized at
the backend boundary (camelCase via CamelModel). The internal retrieval/merge
candidate shape lives with the retrieval/merger code, not here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from teg.domain.base import CamelModel

Bucket = Literal["semantic_plus_historic", "historic_only", "semantic_only"]
SupportType = Literal["direct", "implied"]


class HistoricalTicket(CamelModel):
    """A matched historical Engagement Request, shown for SME selection."""

    ticket_id: str
    title: str
    score: float
    snippet: str = ""


class ValueStreamRecommendation(CamelModel):
    """A recommended Value Stream, resolved to the approved catalogue.

    ``confidence`` is expected in 0.30-1.00 (prompt-guided); we bound it to 0-1 only,
    so a slightly out-of-band model value never fails validation downstream.
    ``reason`` is prompt-guided to <=80 chars; not hard-enforced for the same reason.
    """

    value_stream_id: str
    value_stream_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    support_type: SupportType
    reason: str
    bucket: Bucket
    source_tickets: list[str] = Field(default_factory=list)
