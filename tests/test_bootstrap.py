"""Composition-root wiring test."""

from __future__ import annotations

import pytest

from teg.config.settings import Settings
from teg.services.condense_service import CondenseService


def test_build_condense_service_wires_a_service() -> None:
    pytest.importorskip("markitdown")  # the extractor needs the 'extract' extra
    from teg.bootstrap import build_condense_service

    service = build_condense_service(Settings())
    assert isinstance(service, CondenseService)
