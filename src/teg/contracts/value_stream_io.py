"""Contract B - Value Stream prediction. Backend -> us.

Backend passes back the stored summaryFields. We return ranked recommendations
plus the top-6 historical analogs for the backend's HITL selection step.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from teg.domain.condensed import SummaryFields


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ValueStreamRequest(_Camel):
    ticket_id: str
    summary_fields: SummaryFields
    requested_count: int = 10  # upper bound, not a target
    custom_instruction: str | None = None
    # OPEN #3: only the SME-selected analogs; omit to auto-use the retrieved set.
    selected_historical_ticket_ids: list[str] = Field(default_factory=list)


class RecommendationDTO(_Camel):
    value_stream_id: str
    value_stream_name: str
    confidence: float = Field(ge=0.30, le=1.0)
    support_type: Literal["direct", "implied"]
    reason: str = Field(max_length=80)
    bucket: Literal["semantic_plus_historic", "historic_only", "semantic_only"]
    source_tickets: list[str] = Field(default_factory=list)


class HistoricalTicketDTO(_Camel):
    ticket_id: str
    title: str
    score: float
    snippet: str


class ValueStreamResponse(_Camel):
    ticket_id: str
    recommendations: list[RecommendationDTO]
    historical_tickets: list[HistoricalTicketDTO] = Field(default_factory=list)
    model: str
    prompt_version: str
    latency_ms: int = 0
