"""Composition root.

Assembles services from Settings with their real clients. This is the seam the
backend's adapter calls - build a service once and reuse it (the clients hold
httpx connections for the service's lifetime).
"""

from __future__ import annotations

from teg.condense.config import CondenseConfig
from teg.config.settings import Settings, load_settings
from teg.integrations.files import build_attachment_extractor
from teg.integrations.jira import build_jira_client
from teg.integrations.llm import build_llm_client
from teg.integrations.search import build_search_client
from teg.services.condense_service import CondenseService
from teg.services.value_stream_service import ValueStreamService
from teg.value_stream.config import ValueStreamConfig


def build_condense_service(settings: Settings | None = None) -> CondenseService:
    settings = settings or load_settings()
    config = CondenseConfig(
        doc_char_budget=settings.condense_doc_char_budget,
        max_attachments=settings.condense_max_attachments,
        max_attachment_bytes=settings.condense_max_attachment_bytes,
        min_doc_chars=settings.condense_min_doc_chars,
    )
    return CondenseService(
        build_jira_client(settings),
        build_llm_client(settings),
        build_attachment_extractor(),
        model_name=settings.llm_model,
        config=config,
    )


def build_value_stream_service(settings: Settings | None = None) -> ValueStreamService:
    settings = settings or load_settings()
    config = ValueStreamConfig(
        semantic_fetch_k=settings.vs_semantic_fetch_k,
        historical_fetch_k=settings.vs_historical_fetch_k,
        llm_candidate_window=settings.vs_llm_candidate_window,
        window_headroom=settings.vs_window_headroom,
        max_supporting_tickets=settings.vs_max_supporting_tickets,
    )
    return ValueStreamService(
        build_search_client(settings),
        build_llm_client(settings),
        model_name=settings.llm_model,
        config=config,
    )
