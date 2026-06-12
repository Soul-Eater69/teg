"""Cosmos DB persistence for ingestion (one container, partition key /sourceId)."""

from teg.integrations.cosmos.client import (
    CosmosWriter,
    build_cosmos_writer,
)

__all__ = ["CosmosWriter", "build_cosmos_writer"]
