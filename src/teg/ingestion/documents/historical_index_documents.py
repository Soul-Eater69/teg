"""Build the historical IDMT search-index document (idp_teg_data).

Turns an ingested ticket into the retrieval doc that powers the historic-evidence lane
of VS prediction: content (embedded) + content_vector + properties.{summary, valueStreams}.
content is built the SAME way as the prediction query (build_retrieval_text) so a stored
ticket and a live query share the vector space. value_streams carries the resolved VS GT
(id + name) so a historical hit brings its labels without a Cosmos lookup.
"""

from __future__ import annotations

from teg.domain.condensed import CondensedTicket
from teg.ingestion.extraction.jira_records import ExtractedEngagementRequest
from teg.ingestion.ground_truth.theme_ground_truth import ThemeGroundTruth
from teg.value_stream.retrieval import build_retrieval_text

SOURCE = "Jira"
ENTITY_TYPE = "EngagementRequest"


def build_historical_content(condensed: CondensedTicket) -> str:
    """Retrieval text embedded for the historical index (matches the prediction query)."""
    return build_retrieval_text(condensed.summary_fields)


def build_historical_index_document(
    *,
    er: ExtractedEngagementRequest,
    condensed: CondensedTicket,
    theme_gt: list[ThemeGroundTruth],
    content_vector: list[float] | None = None,
) -> dict:
    return {
        "id": er.stable_id,
        "source": SOURCE,
        "sourceId": er.key or None,
        "entityType": ENTITY_TYPE,
        "content": build_historical_content(condensed),
        "content_vector": content_vector,
        "properties": {
            "summary": condensed.summary_fields.generated_summary,
            "valueStreams": [_label(gt) for gt in theme_gt],
        },
    }


def _label(gt: ThemeGroundTruth) -> dict:
    return {
        "valueStreamId": gt.value_stream_id,
        "valueStreamName": gt.value_stream_name,
    }
