"""Composition root.

Assembles services from Settings with their real clients. This is the seam the
backend's adapter calls - build a service once and reuse it (the clients hold
httpx connections for the service's lifetime).
"""

from __future__ import annotations

from teg.condense.config import CondenseConfig
from teg.config.settings import Settings, load_settings
from teg.integrations.embeddings import build_embeddings_client
from teg.integrations.files import build_attachment_extractor
from teg.integrations.jira import build_jira_client
from teg.integrations.llm import build_llm_client
from teg.integrations.search import ValueStreamHit, build_search_client
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.ingestion.extraction.jira_source import build_jira_ingestion_source
from teg.ingestion.pipeline.idmt_ingestion import IdmtIngestion
from teg.services.condense_service import CondenseService
from teg.services.theme_service import ThemeService
from teg.services.value_stream_service import ValueStreamService
from teg.theme.stage_catalogue import StageCatalogue
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


def build_idmt_ingestion(
    settings: Settings | None = None, *, catalogue_path: str | None = None, embed: bool = False
) -> IdmtIngestion:
    # catalogue_path is no longer needed (VS comes from each theme's Business Value Stream
    # field, not a catalogue match); kept optional for backward-compatible callers.
    settings = settings or load_settings()
    return IdmtIngestion(
        jira_source=build_jira_ingestion_source(settings),
        condense_service=build_condense_service(settings),
        embeddings_client=build_embeddings_client(settings) if embed else None,
    )


def build_value_stream_service(
    settings: Settings | None = None,
    *,
    config: ValueStreamConfig | None = None,
    catalogue_path: str = "data/value_stream_capability_map.json",
    historic_content: dict[str, dict] | None = None,
) -> ValueStreamService:
    settings = settings or load_settings()
    catalogue = _load_vs_catalogue(catalogue_path)
    # Per-VS selection context (used to enrich candidate blocks).
    vs_details = {
        vs.value_stream_id: {
            "description": vs.value_stream_description,
            "category": vs.category,
            "trigger": vs.trigger,
            "valueProposition": vs.value_proposition,
        }
        for vs in catalogue
    }
    # The 50 VS as candidates straight from the governed catalogue - so the VS lane no longer needs
    # the search index (the index holds only historic docs). score=0: ranking is unused (scores off).
    vs_candidates = [
        ValueStreamHit(
            value_stream_id=vs.value_stream_id, value_stream_name=vs.value_stream_name,
            value_stream_description=vs.value_stream_description, category=vs.category,
            trigger=vs.trigger, value_proposition=vs.value_proposition, score=0.0,
        )
        for vs in catalogue
    ] or None  # None -> fall back to index search when the catalogue is empty (tests/fakes)
    # Retrieval/window tuning lives in ValueStreamConfig (code default, eval-tuned),
    # not env - env is for secrets + per-deployment infra only. config override is for eval.
    return ValueStreamService(
        build_search_client(settings),
        build_llm_client(settings),
        model_name=settings.llm_model,
        config=config or ValueStreamConfig(),
        vs_details=vs_details,
        historic_content=historic_content,
        vs_candidates=vs_candidates,
    )


def _load_vs_catalogue(path: str):
    try:
        return load_value_stream_catalogue(path)
    except Exception:
        return []  # catalogue optional for tests / fakes; index id+name still works


def build_theme_service(settings: Settings | None = None, *, catalogue_path: str) -> ThemeService:
    settings = settings or load_settings()
    # Governed stage catalogue from the Sightline map (from Cosmos once that read exists).
    catalogue = StageCatalogue.from_catalogue(load_value_stream_catalogue(catalogue_path))
    return ThemeService(catalogue, build_llm_client(settings), model_name=settings.llm_model)
