"""Composition root.

Assembles services from Settings with their real clients. This is the seam the
backend's adapter calls - build a service once and reuse it (the clients hold
httpx connections for the service's lifetime).
"""

from __future__ import annotations

from teg.config.settings import Settings, load_settings
from teg.integrations.files import build_attachment_extractor
from teg.integrations.jira import build_jira_client
from teg.integrations.llm import build_llm_client
from teg.services.condense_service import CondenseService


def build_condense_service(settings: Settings | None = None) -> CondenseService:
    settings = settings or load_settings()
    return CondenseService(
        build_jira_client(settings),
        build_llm_client(settings),
        build_attachment_extractor(),
        model_name=settings.llm_model,
    )
