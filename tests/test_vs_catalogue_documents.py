"""VS catalogue loader + Cosmos/index document builders (Generator A)."""

from __future__ import annotations

import json

from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.ingestion.documents.value_stream_documents import (
    build_catalogue_content,
    build_catalogue_document,
    build_index_document,
)

SAMPLE = {
    "source_file": "value_streams.xlsx",
    "value_stream_count": 1,
    "value_streams": [
        {
            "value_stream_id": "VSR00074583",
            "value_stream_name": "Acquire Asset",
            "value_stream_description": "The end-to-end view from request to delivery",
            "value_stream_category": "Finance",
            "value_stream_trigger": "Asset Requester",
            "value_stream_stakeholders": "Supplier; Procurement; Asset Requestor",
            "value_stream_created_date": "2021-03-14",
            "stages": [
                {
                    "stage_id": "VSS00074680",
                    "stage_sequence": 1,
                    "stage_name": "Request Asset",
                    "stage_display_name": "Request Asset {VSS00074680}",
                    "stage_description": "The act of submitting a request for a new asset",
                    "stage_entrance_criteria": "Asset order initiated",
                    "stage_exit_criteria": "Asset order acknowledged",
                    "stage_value_items": "Asset order requested",
                    "stage_stakeholders": "Asset Requestor; Procurement",
                }
            ],
        }
    ],
}


def _load(tmp_path):
    path = tmp_path / "map.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return load_value_stream_catalogue(path)


def test_loader_parses_and_splits_semicolons(tmp_path) -> None:
    catalogue = _load(tmp_path)
    assert len(catalogue) == 1
    vs = catalogue[0]
    assert vs.value_stream_id == "VSR00074583"
    assert vs.value_stream_stakeholders == ["Supplier", "Procurement", "Asset Requestor"]
    assert vs.stages[0].stage_sequence == 1
    assert vs.stages[0].stage_stakeholders == ["Asset Requestor", "Procurement"]


def test_catalogue_document_shape(tmp_path) -> None:
    vs = _load(tmp_path)[0]
    doc = build_catalogue_document(vs)
    assert doc["id"] == "VSR00074583"
    assert doc["entityType"] == "valueStream"
    assert doc["createdAt"] == "2021-03-14"
    props = doc["properties"]
    assert props["valueStreamCategory"] == "Finance"
    assert props["valueStreamTrigger"] == "Asset Requester"
    stage = props["valueStages"][0]
    assert stage["stageId"] == "VSS00074680"
    assert stage["stageSequence"] == 1
    assert stage["stageEntranceCriteria"] == "Asset order initiated"
    assert "capabilitiesL2" not in stage  # L2/L3 dropped from this pass


def test_index_document_content_and_props(tmp_path) -> None:
    vs = _load(tmp_path)[0]
    content = build_catalogue_content(vs)
    assert "Acquire Asset" in content and "Finance" in content and "Asset Requester" in content

    doc = build_index_document(vs, content_vector=[0.1, 0.2])
    assert doc["id"] == "VSR00074583"
    assert doc["content"] == content
    assert doc["content_vector"] == [0.1, 0.2]
    assert doc["properties"]["valueStreamCategory"] == "Finance"
    assert "valueStages" not in doc["properties"]  # index never carries the stage hierarchy
