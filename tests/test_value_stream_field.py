"""Parsing the Business Value Stream field ('<name> {<id>}') into (name, id)."""

from __future__ import annotations

from teg.ingestion.extraction.value_stream_field import parse_value_stream


def test_plain_string() -> None:
    assert parse_value_stream("configure price {VS1024}") == ("configure price", "VS1024")
    assert parse_value_stream("Configure, Price and Quote {VSR00074586}") == (
        "Configure, Price and Quote", "VSR00074586")


def test_whitespace_tolerant() -> None:
    assert parse_value_stream("  Resolve Appeal  { VSR00074590 } ") == ("Resolve Appeal", "VSR00074590")


def test_select_object_and_list() -> None:
    assert parse_value_stream({"value": "Receive Care {VS9}"}) == ("Receive Care", "VS9")
    assert parse_value_stream({"name": "Issue Payment {VS3}"}) == ("Issue Payment", "VS3")
    assert parse_value_stream([{"value": "Adjudicate Claim {VS5}"}]) == ("Adjudicate Claim", "VS5")


def test_absent_or_unparseable_is_none() -> None:
    assert parse_value_stream(None) is None
    assert parse_value_stream("") is None
    assert parse_value_stream("no braces here") is None
    assert parse_value_stream([]) is None
