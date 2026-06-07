"""Contract B - Value Stream prediction. Backend -> us.

Backend replays the stored summaryFields. We return ranked recommendations plus the
top-6 historical analogs for the backend's HITL selection step. The records live in
``teg.domain.value_stream`` (single source of truth); this module adds the request /
response envelope.
"""

from __future__ import annotations

from pydantic import Field

from teg.domain.base import CamelModel
from teg.domain.condensed import SummaryFields
from teg.domain.value_stream import HistoricalTicket, ValueStreamRecommendation


class ValueStreamRequest(CamelModel):
    ticket_id: str
    summary_fields: SummaryFields
    requested_count: int = 10  # default 10; upper bound, not a target
    custom_instruction: str | None = None
    # Only the SME-selected analogs; omit to auto-use the retrieved set.
    selected_historical_ticket_ids: list[str] = Field(default_factory=list)


class ValueStreamResponse(CamelModel):
    ticket_id: str
    recommendations: list[ValueStreamRecommendation]
    historical_tickets: list[HistoricalTicket] = Field(default_factory=list)
    model: str
    prompt_version: str
    latency_ms: int = 0


__all__ = [
    "ValueStreamRequest",
    "ValueStreamResponse",
    "HistoricalTicket",
    "ValueStreamRecommendation",
]
