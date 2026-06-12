"""AzureCosmosWriter with a fake azure client (no live Cosmos calls)."""

from __future__ import annotations

import pytest

from teg.integrations.cosmos.client import AzureCosmosWriter, _validate


class _FakeContainer:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}

    async def upsert_item(self, doc: dict) -> dict:
        self.items[doc["id"]] = doc  # keyed by id => re-upsert overwrites (idempotent)
        return doc


class _FakeDatabase:
    def __init__(self, container: _FakeContainer) -> None:
        self._container = container

    def get_container_client(self, name: str) -> _FakeContainer:
        return self._container


class _FakeClient:
    def __init__(self) -> None:
        self.container = _FakeContainer()
        self.closed = False

    def get_database_client(self, name: str) -> _FakeDatabase:
        return _FakeDatabase(self.container)

    async def close(self) -> None:
        self.closed = True


def _doc(doc_id: str, source_id: str, entity_type: str) -> dict:
    # Cosmos docs carry the hierarchical partition key paths (domain + entityType).
    return {"id": doc_id, "domain": "WORKITEM", "entityType": entity_type,
            "sourceId": source_id, "key": f"K-{source_id}"}


async def test_upsert_writes_all_docs() -> None:
    client = _FakeClient()
    writer = AzureCosmosWriter(client, "db", "teg_data")

    n = await writer.upsert([
        _doc("u1", "3364549", "EngagementRequest"),
        _doc("u2", "9981", "Theme"),
        _doc("u3", "VSR00074590", "ValueStream"),
    ])

    assert n == 3
    assert set(client.container.items) == {"u1", "u2", "u3"}
    assert client.container.items["u3"]["entityType"] == "ValueStream"


async def test_upsert_is_idempotent_on_id() -> None:
    client = _FakeClient()
    writer = AzureCosmosWriter(client, "db", "teg_data")

    await writer.upsert([_doc("u1", "3364549", "EngagementRequest")])
    await writer.upsert([_doc("u1", "3364549", "EngagementRequest")])  # same id => overwrite

    assert len(client.container.items) == 1


async def test_close_closes_client() -> None:
    client = _FakeClient()
    await AzureCosmosWriter(client, "db", "teg_data").close()
    assert client.closed is True


def test_validate_requires_id_and_both_partition_paths() -> None:
    with pytest.raises(ValueError, match="missing 'id'"):
        _validate({"domain": "WORKITEM", "entityType": "THEME"})
    with pytest.raises(ValueError, match="partition key 'domain'"):
        _validate({"id": "u1", "entityType": "THEME"})
    with pytest.raises(ValueError, match="partition key 'entityType'"):
        _validate({"id": "u1", "domain": "WORKITEM"})
