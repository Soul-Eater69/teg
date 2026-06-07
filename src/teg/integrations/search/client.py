"""Search protocols + records for the two VS retrieval lanes (TDD 5.3).

VS retrieval depends on these protocols, not a concrete Azure client, so it is
unit-tested with fakes. The real Azure AI Search implementation (TEG-34) lands
alongside this module and is configured from Settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class HistoricalValueStreamLabel:
    """A Value Stream the historical ER was linked to (its ground truth)."""

    value_stream_id: str
    value_stream_name: str
    support_type: str = ""  # direct | implied | weak | unsupported
    reason: str = ""
    evidence: str = ""


@dataclass
class ValueStreamHit:
    """A VS-catalogue lane hit."""

    value_stream_id: str
    value_stream_name: str
    value_stream_description: str = ""
    score: float = 0.0  # hybrid relevance score


@dataclass
class HistoricalHit:
    """A historical Engagement Request lane hit, with the VS labels it carries."""

    ticket_id: str
    title: str
    score: float = 0.0  # vector similarity
    snippet: str = ""
    value_streams: list[HistoricalValueStreamLabel] = field(default_factory=list)


@runtime_checkable
class SearchClient(Protocol):
    async def search_value_streams(
        self, query: str, query_vector: list[float], *, top_k: int = 50
    ) -> list[ValueStreamHit]:
        """VS-catalogue lane: hybrid (text + vector) over the valueStream documents."""
        ...

    async def search_historical(
        self, query_vector: list[float], *, top_k: int = 6
    ) -> list[HistoricalHit]:
        """Historical-ER lane: vector similarity over EngagementRequest documents."""
        ...
