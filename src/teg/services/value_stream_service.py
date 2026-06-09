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
from teg.value_stream.candidate_merger import build_candidates, derive_runtime, select_review_pool
from teg.value_stream.config import ValueStreamConfig
from teg.value_stream.custom_instruction import parse_requested_count
from teg.value_stream.retrieval import retrieve
from teg.value_stream.selection import select_value_streams


class ValueStreamService:
    def __init__(
        self,
        search_client: SearchClient,
        llm_client: LLMClient,
        *,
        model_name: str = "",
        config: ValueStreamConfig = ValueStreamConfig(),
    ) -> None:
        self._search = search_client
        self._llm = llm_client
        self._model_name = model_name
        self._config = config

    async def predict(self, request: ValueStreamRequest) -> ValueStreamResponse:
        # The custom instruction may only set the count: parse it deterministically (the raw
        # text never reaches a prompt); a parsed count overrides requested_count.
        requested_count = parse_requested_count(request.custom_instruction) or request.requested_count

        # Fetch sizes + merge policy adapt to the requested count and the tuning config.
        vs_top_k, historical_top_k, policy = derive_runtime(requested_count, config=self._config)
        # Over-fetch by the exclude count so dropping self/excluded tickets still leaves a
        # full analog set.
        result = await retrieve(
            request.summary_fields,
            self._search,
            vs_top_k=vs_top_k,
            historical_top_k=historical_top_k + len(request.exclude_ticket_ids),
            include_historical=self._config.use_historic_lane,
        )
        historical_hits = _excluding(result.historical_hits, request.exclude_ticket_ids)[:historical_top_k]
        # SME-selected analogs become the evidence used for ranking (all retrieved if
        # none selected); the full retrieved set is still returned for the HITL step.
        evidence = _selected(historical_hits, request.selected_historical_ticket_ids)
        candidates = build_candidates(
            result.value_stream_hits,
            evidence,
            max_supporting_tickets=policy.max_supporting_tickets,
            use_classification=self._config.use_historic_classification,
        )
        review_pool = select_review_pool(candidates, policy=policy)
        recommendations = await select_value_streams(
            query=request.summary_fields.generated_summary,
            candidates=review_pool,
            requested_count=requested_count,
            llm_client=self._llm,
        )
        return ValueStreamResponse(
            ticket_id=request.ticket_id,
            recommendations=recommendations,
            historical_tickets=[_to_ticket(hit) for hit in historical_hits],
            model=self._model_name,
        )


def _excluding(hits: list[HistoricalHit], exclude_ids: list[str]) -> list[HistoricalHit]:
    if not exclude_ids:
        return hits
    drop = set(exclude_ids)
    return [hit for hit in hits if hit.ticket_id not in drop]


def _selected(hits: list[HistoricalHit], selected_ids: list[str]) -> list[HistoricalHit]:
    if not selected_ids:
        return hits
    keep = set(selected_ids)
    return [hit for hit in hits if hit.ticket_id in keep]


def _to_ticket(hit: HistoricalHit) -> HistoricalTicket:
    return HistoricalTicket(
        ticket_id=hit.ticket_id, title=hit.title, score=hit.score, snippet=hit.snippet
    )
