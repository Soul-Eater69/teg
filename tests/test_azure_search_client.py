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
    doc = {
        "id": "VSR01261896",
        "properties": {
            "valueStreamId": "VSR01261896",
            "valueStreamName": "Resolve Privacy Incident",
            "valueStreamDescription": "Ensuring regulatory compliance for select data breaches",
            "category": "Compliance",
            "trigger": "Reported breach",
            "valueProposition": "Limit regulatory exposure",
        },
        "@search.score": 1.0,
    }
    hit = _to_value_stream_hit(doc)
    assert hit.value_stream_id == "VSR01261896"
    assert hit.value_stream_name == "Resolve Privacy Incident"
    assert hit.value_stream_description.startswith("Ensuring")
    assert hit.category == "Compliance"
    assert hit.trigger == "Reported breach"
    assert hit.value_proposition == "Limit regulatory exposure"
    assert hit.score == 1.0


def test_value_stream_hit_prefers_reranker_score() -> None:
    doc = {"properties": {"valueStreamId": "VS1"}, "@search.score": 0.03, "@search.reranker_score": 2.7}
    assert _to_value_stream_hit(doc).score == 2.7


def test_historical_hit_maps_native_value_streams() -> None:
    doc = {
        "id": "3364549",
        "sourceId": "IDMT-8280",
        "@search.score": 0.82,
        "properties": {
            "summary": "BH enhancements initiative adds suicide prevention",
            "valueStreams": [
                {
                    "valueStreamId": "VSR00074586",
                    "valueStreamName": "Configure, Price, and Quote",
                    "supportType": "direct",
                    "reason": "references Salesforce LGNA",
                    "evidence": "Salesforce LGNA quoting",
                }
            ],
        },
    }
    hit = _to_historical_hit(doc)
    assert hit.ticket_id == "IDMT-8280"  # sourceId preferred over stable id
    assert hit.snippet.startswith("BH enhancements")
    assert hit.score == 0.82
    label = hit.value_streams[0]
    assert label.value_stream_id == "VSR00074586"
    assert label.support_type == "direct"
    assert label.evidence == "Salesforce LGNA quoting"


def test_historical_hit_prefers_reranker_score() -> None:
    # historical lane is now hybrid+semantic -> prefer the reranker score
    doc = {"sourceId": "IDMT-1", "@search.score": 0.03, "@search.reranker_score": 2.7,
           "properties": {"summary": "s", "valueStreams": []}}
    assert _to_historical_hit(doc).score == 2.7


def test_parse_value_streams_tolerates_bad_input() -> None:
    assert _parse_value_streams(None) == []
    assert _parse_value_streams("not a list") == []
    assert _parse_value_streams([]) == []
    assert _parse_value_streams([{"valueStreamName": "n"}]) == []  # no id -> skipped
    parsed = _parse_value_streams([{"valueStreamId": "VS1", "supportType": "implied"}])
    assert parsed[0].value_stream_id == "VS1" and parsed[0].support_type == "implied"
