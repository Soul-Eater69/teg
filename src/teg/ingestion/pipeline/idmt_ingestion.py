"""IDMT ingestion pipeline: live Jira -> Cosmos IDMT/ER + Theme documents.

Per ticket: fetch the ER + its linked themes, condense the idea card, resolve each
theme's Value Stream against the catalogue, classify it direct/implied, then build the
ER doc (with themes[] GT) and one Theme doc per linked theme. Themes whose VS does not
resolve to an approved value stream are dropped from the GT.
"""

from __future__ import annotations

from teg.contracts.condense_io import CondenseRequest
from teg.ingestion.documents.idmt_documents import build_idmt_document, build_theme_document
from teg.ingestion.extraction.jira_source import JiraIngestionSource
from teg.ingestion.ground_truth.theme_ground_truth import ThemeGroundTruth
from teg.ingestion.ground_truth.value_stream_classification import classify_value_streams
from teg.ingestion.ground_truth.value_stream_match import ValueStreamResolver
from teg.integrations.llm import LLMClient
from teg.services.condense_service import CondenseService


class IdmtIngestion:
    def __init__(
        self,
        *,
        jira_source: JiraIngestionSource,
        condense_service: CondenseService,
        resolver: ValueStreamResolver,
        llm_client: LLMClient,
    ) -> None:
        self._jira = jira_source
        self._condense = condense_service
        self._resolver = resolver
        self._llm = llm_client

    async def ingest(self, ticket_id: str) -> tuple[dict, list[dict]]:
        """Return (idmt_document, theme_documents) for one IDMT ticket."""
        er = await self._jira.fetch_engagement_request(ticket_id)
        condensed = (await self._condense.condense(CondenseRequest(ticket_id=ticket_id))).condensed

        resolved = await self._resolver.resolve([t.summary for t in er.themes], self._llm)
        vs_names = [hit[1] for hit in resolved.values() if hit]
        classification = await classify_value_streams(
            ticket_id=ticket_id,
            text=condensed.raw_text,
            value_stream_names=vs_names,
            llm_client=self._llm,
        )

        theme_gt: list[ThemeGroundTruth] = []
        for theme in er.themes:
            hit = resolved.get(theme.summary)
            if not hit:
                continue  # VS did not resolve to an approved value stream - drop
            vs_id, vs_name = hit
            label = classification.get(vs_name)
            theme_gt.append(
                ThemeGroundTruth(
                    theme_stable_id=theme.stable_id,
                    group_key=theme.group_key,
                    value_stream_id=vs_id,
                    value_stream_name=vs_name,
                    support_type=label.inference_type if label else "implied",
                    reason=label.reason if label else "",
                )
            )

        idmt_doc = build_idmt_document(er=er, condensed=condensed, theme_gt=theme_gt)
        theme_docs = [build_theme_document(theme, parent_er_id=er.stable_id) for theme in er.themes]
        return idmt_doc, theme_docs
