"""IDMT ingestion pipeline: live Jira -> Cosmos IDMT/ER + Theme + historical index docs.

Per ticket: fetch the ER + its linked themes, condense the idea card, resolve each
theme's Value Stream against the catalogue, then build the ER doc (with themes[] GT), one
Theme doc per linked theme, and the historical search-index doc (embedded when an embeddings
client is provided). Themes whose VS does not resolve to an approved value stream are dropped
from the GT.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from teg.contracts.condense_io import CondenseRequest
from teg.ingestion.documents.historical_index_documents import (
    build_historical_content,
    build_historical_index_document,
)
from teg.ingestion.documents.idmt_documents import build_idmt_document, build_theme_document
from teg.ingestion.extraction.jira_source import JiraIngestionSource
from teg.ingestion.ground_truth.theme_ground_truth import ThemeGroundTruth
from teg.ingestion.ground_truth.value_stream_match import ValueStreamResolver
from teg.integrations.embeddings import EmbeddingsClient
from teg.integrations.llm import LLMClient
from teg.services.condense_service import CondenseService


@dataclass(frozen=True)
class IngestedTicket:
    """All documents produced for one ingested IDMT ticket."""

    idmt_document: dict  # Cosmos IDMT/ER doc
    theme_documents: list[dict]  # Cosmos Theme docs
    historical_index_document: dict  # idp_teg_data search doc


class IdmtIngestion:
    def __init__(
        self,
        *,
        jira_source: JiraIngestionSource,
        condense_service: CondenseService,
        resolver: ValueStreamResolver,
        llm_client: LLMClient,
        embeddings_client: EmbeddingsClient | None = None,
    ) -> None:
        self._jira = jira_source
        self._condense = condense_service
        self._resolver = resolver
        self._llm = llm_client
        self._embeddings = embeddings_client

    async def ingest(self, ticket_id: str) -> IngestedTicket:
        """Build the Cosmos IDMT/Theme docs + the historical index doc for one ticket."""
        # The ER fetch (+ linked themes) and condense are independent - run concurrently.
        er, condense_response = await asyncio.gather(
            self._jira.fetch_engagement_request(ticket_id),
            self._condense.condense(CondenseRequest(ticket_id=ticket_id)),
        )
        condensed = condense_response.condensed

        resolved = await self._resolver.resolve([t.summary for t in er.themes], self._llm)

        # Only themes that resolve to an approved VS are kept - both as GT and as a
        # Theme doc - so every Theme doc is referenced by a themes[] entry (no orphans).
        theme_gt: list[ThemeGroundTruth] = []
        theme_docs: list[dict] = []
        for theme in er.themes:
            hit = resolved.get(theme.summary)
            if not hit:
                continue  # VS did not resolve to an approved value stream - drop entirely
            vs_id, vs_name = hit
            theme_gt.append(
                ThemeGroundTruth(
                    theme_stable_id=theme.stable_id,
                    group_key=theme.group_key,
                    value_stream_id=vs_id,
                    value_stream_name=vs_name,
                )
            )
            theme_docs.append(build_theme_document(theme, parent_er_id=er.stable_id))

        idmt_doc = build_idmt_document(er=er, condensed=condensed, theme_gt=theme_gt)

        content_vector = None
        if self._embeddings is not None:
            content_vector = await self._embeddings.embed(build_historical_content(condensed))
        historical_doc = build_historical_index_document(
            er=er, condensed=condensed, theme_gt=theme_gt, content_vector=content_vector
        )
        return IngestedTicket(
            idmt_document=idmt_doc,
            theme_documents=theme_docs,
            historical_index_document=historical_doc,
        )
