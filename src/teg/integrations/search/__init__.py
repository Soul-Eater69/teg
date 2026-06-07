"""Search integration: protocol + records (Azure AI Search impl in TEG-34)."""

from teg.integrations.search.client import (
    HistoricalHit,
    HistoricalValueStreamLabel,
    SearchClient,
    ValueStreamHit,
)

__all__ = [
    "SearchClient",
    "ValueStreamHit",
    "HistoricalHit",
    "HistoricalValueStreamLabel",
]
