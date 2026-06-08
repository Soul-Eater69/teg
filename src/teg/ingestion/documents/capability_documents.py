"""Build Cosmos documents for the standalone capability tree (L1/L2/L3 hierarchy).

One document per capability node, keyed by capabilityId, with parentId pointing at its
parent capability (L3 -> L2 -> L1). This is the canonical capability hierarchy used for
lookups (e.g. resolving a predicted L3's parent L2).
"""

from __future__ import annotations

from datetime import datetime, timezone

from teg.ingestion.catalogues.models import CapabilityNode

CATALOGUE_SOURCE = "Sightline"
ENTITY_TYPE = "capability"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_capability_document(node: CapabilityNode, *, ingested_at: str | None = None) -> dict:
    return {
        "id": node.capability_id,
        "source": CATALOGUE_SOURCE,
        "entityType": ENTITY_TYPE,
        "parentId": node.parent_id or None,
        "parentEntityType": ENTITY_TYPE if node.parent_id else None,
        "ingestedAt": ingested_at or _utc_now(),
        "properties": {
            "capabilityId": node.capability_id,
            "capabilityName": node.capability_name,
            "capabilityDescription": node.capability_description,
            "level": node.level,
            "tier": node.tier,
            "active": node.active,
        },
    }
