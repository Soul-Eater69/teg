"""Unified-index result mapping (pure; no SDK needed).

Docs come back with our generated nested ``properties`` shape; entityType is the lane.
"""

from __future__ import annotations

from teg.integrations.search.azure_client import (
    _parse_value_streams,
    _to_historical_hit,
    _to_value_stream_hit,
)


def test_value_stream_hit_mapping() -> None:
    # lean index: the VS hit carries only id + name + score; the rest is enriched from the catalogue.
    doc = {
        "key": "Resolve Privacy Incident",
        "properties": {
            "valueStreamId": "VSR01261896",
            "valueStreamName": "Resolve Privacy Incident",
        },
        "@search.score": 1.0,
    }
    hit = _to_value_stream_hit(doc)
    assert hit.value_stream_id == "VSR01261896"
    assert hit.value_stream_name == "Resolve Privacy Incident"
    assert hit.score == 1.0
    assert hit.trigger == ""  # not in the index anymore


def test_value_stream_hit_prefers_reranker_score() -> None:
    doc = {"properties": {"valueStreamId": "VS1"}, "@search.score": 0.03, "@search.reranker_score": 2.7}
    assert _to_value_stream_hit(doc).score == 2.7


def test_historical_hit_is_retrieval_only_vs_enriched_later() -> None:
    # The index is retrieval-only: a hit carries id + searchText + score, NOT the VS labels (those
    # come from Cosmos by key, enriched by the service).
    doc = {
        "key": "IDMT-8280",
        "sourceId": "3364549",
        "@search.score": 0.82,
        "searchText": "BH enhancements initiative adds suicide prevention",
    }
    hit = _to_historical_hit(doc)
    assert hit.ticket_id == "IDMT-8280"  # key (IDMT-####) = the leave-one-out match key
    assert hit.snippet.startswith("BH enhancements")
    assert hit.score == 0.82
    assert hit.value_streams == []  # not in the index - enriched downstream from Cosmos


def test_historical_hit_normalizes_reranker_score() -> None:
    # historical lane is hybrid+semantic -> use the reranker score, normalized 0-4 -> 0-1
    doc = {"sourceId": "IDMT-1", "@search.score": 0.03, "@search.reranker_score": 2.8,
           "properties": {"summary": "s", "valueStreams": []}}
    assert _to_historical_hit(doc).score == 0.7  # 2.8 / 4


def test_historical_hit_falls_back_to_raw_score() -> None:
    doc = {"sourceId": "IDMT-1", "@search.score": 0.82, "properties": {"summary": "s", "valueStreams": []}}
    assert _to_historical_hit(doc).score == 0.82  # no reranker -> raw score (already 0-1)


def test_parse_value_streams_tolerates_bad_input() -> None:
    assert _parse_value_streams(None) == []
    assert _parse_value_streams("not a list") == []
    assert _parse_value_streams([]) == []
    assert _parse_value_streams([{"valueStreamName": "n"}]) == []  # no id -> skipped
    parsed = _parse_value_streams([{"valueStreamId": "VS1", "valueStreamName": "n"}])
    assert parsed[0].value_stream_id == "VS1" and parsed[0].value_stream_name == "n"
