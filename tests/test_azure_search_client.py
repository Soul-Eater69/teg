"""Azure search result mapping + value_streams_json parsing (pure; no SDK needed)."""

from __future__ import annotations

from teg.integrations.search.azure_client import (
    _parse_value_streams_json,
    _to_historical_hit,
    _to_value_stream_hit,
)


def test_value_stream_hit_mapping() -> None:
    doc = {
        "entity_id": "VSR01261896",
        "entity_name": "Resolve Privacy Incident",
        "content": "Ensuring regulatory compliance for select data breaches",
        "@search.score": 1.0,
    }
    hit = _to_value_stream_hit(doc)
    assert hit.value_stream_id == "VSR01261896"
    assert hit.value_stream_name == "Resolve Privacy Incident"
    assert hit.value_stream_description.startswith("Ensuring")
    assert hit.score == 1.0


def test_value_stream_hit_prefers_reranker_score() -> None:
    doc = {"entity_id": "VS1", "entity_name": "n", "@search.score": 0.03, "@search.reranker_score": 2.7}
    assert _to_value_stream_hit(doc).score == 2.7


def test_historical_hit_parses_value_streams_json() -> None:
    doc = {
        "ticket_id": "IDMT-8280",
        "summary_text": "BH enhancements initiative adds suicide prevention",
        "@search.score": 0.82,
        "value_streams_json": (
            '[{"vs_id": "VSR00074586", "vs_name": "Configure, Price, and Quote", '
            '"inference_type": "direct", "reason": "references Salesforce LGNA"}]'
        ),
    }
    hit = _to_historical_hit(doc)
    assert hit.ticket_id == "IDMT-8280"
    assert hit.snippet.startswith("BH enhancements")
    assert hit.score == 0.82
    assert len(hit.value_streams) == 1
    label = hit.value_streams[0]
    assert label.value_stream_id == "VSR00074586"
    assert label.value_stream_name == "Configure, Price, and Quote"
    assert label.support_type == "direct"
    assert "Salesforce" in label.reason


def test_parse_value_streams_json_tolerates_bad_input() -> None:
    assert _parse_value_streams_json(None) == []
    assert _parse_value_streams_json("not json") == []
    assert _parse_value_streams_json("[]") == []
    parsed = _parse_value_streams_json([{"vs_id": "VS1", "vs_name": "n", "inference_type": "implied"}])
    assert parsed[0].value_stream_id == "VS1"
    assert parsed[0].support_type == "implied"
