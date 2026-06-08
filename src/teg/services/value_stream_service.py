"""Value Stream prediction service facade (Contract B).

The backend calls :meth:`ValueStreamService.predict`. Wires the pipeline:
retrieve (two lanes) -> build candidates + merge -> review-pool LLM selection.
Clients are injected so it can be unit-tested with fakes.
"""

from __future__ import annotations

from teg.contracts.value_stream_io import ValueStreamRequest, ValueStreamResponse
from teg.domain.value_stream import HistoricalTicket
from teg.integrations.llm import LLMClient
from teg.integrations.search import HistoricalHit, SearchClient
from teg.value_stream.candidate_merger import build_candidates, select_review_pool
from teg.value_stream.models import CandidateMergePolicy
from teg.value_stream.retrieval import retrieve
from teg.value_stream.selection import select_value_streams


class ValueStreamService:
    def __init__(
        self,
        search_client: SearchClient,
        llm_client: LLMClient,
        *,
        model_name: str = "",
        policy: CandidateMergePolicy = CandidateMergePolicy(),
    ) -> None:
        self._search = search_client
        self._llm = llm_client
        self._model_name = model_name
        self._policy = policy

    async def predict(self, request: ValueStreamRequest) -> ValueStreamResponse:
        result = await retrieve(request.summary_fields, self._search)
        # SME-selected analogs become the evidence used for ranking (all six if none
        # selected); the full retrieved set is still returned for the HITL step.
        evidence = _selected(result.historical_hits, request.selected_historical_ticket_ids)
        candidates = build_candidates(result.value_stream_hits, evidence)
        review_pool = select_review_pool(candidates, policy=self._policy)
        recommendations = await select_value_streams(
            query=request.summary_fields.generated_summary,
            candidates=review_pool,
            requested_count=request.requested_count,
            llm_client=self._llm,
            custom_instruction=request.custom_instruction,
        )
        return ValueStreamResponse(
            ticket_id=request.ticket_id,
            recommendations=recommendations,
            historical_tickets=[_to_ticket(hit) for hit in result.historical_hits],
            model=self._model_name,
        )


def _selected(hits: list[HistoricalHit], selected_ids: list[str]) -> list[HistoricalHit]:
    if not selected_ids:
        return hits
    keep = set(selected_ids)
    return [hit for hit in hits if hit.ticket_id in keep]


def _to_ticket(hit: HistoricalHit) -> HistoricalTicket:
    return HistoricalTicket(
        ticket_id=hit.ticket_id, title=hit.title, score=hit.score, snippet=hit.snippet
    )
