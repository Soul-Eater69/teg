"""Value Stream prediction records (TDD 5.3-5.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Bucket = Literal["semantic_plus_historic", "historic_only", "semantic_only"]
SupportType = Literal["direct", "implied"]


@dataclass
class HistoricalTicket:
    """One of the top-6 matched historical Engagement Requests shown for review."""

    ticket_id: str
    title: str
    score: float
    snippet: str


@dataclass
class ValueStreamRecommendation:
    """A single recommended Value Stream, resolved to the approved catalogue."""

    value_stream_id: str
    value_stream_name: str
    confidence: float  # 0.30-1.00
    support_type: SupportType
    reason: str  # <= 80 chars, names the operational link for implied picks
    bucket: Bucket
    source_tickets: list[str] = field(default_factory=list)  # set when historical support used


@dataclass
class ValueStreamResult:
    """Full VS prediction output: ranked recommendations + analogs for HITL."""

    ticket_id: str
    recommendations: list[ValueStreamRecommendation]
    historical_tickets: list[HistoricalTicket] = field(default_factory=list)
