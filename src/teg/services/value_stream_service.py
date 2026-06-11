"""Value Stream prediction service facade (Contract B).

The backend calls :meth:`ValueStreamService.predict`. Wires the pipeline:
retrieve (two lanes) -> build candidates + merge -> review-pool LLM selection.
Clients are injected so it can be unit-tested with fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from teg.contracts.value_stream_io import ValueStreamRequest, ValueStreamResponse
from teg.domain.value_stream import HistoricalTicket
from teg.integrations.llm import LLMClient
from teg.integrations.search import HistoricalHit, SearchClient
from teg.value_stream.candidate_merger import build_candidates, derive_runtime, select_review_pool
from teg.value_stream.config import ValueStreamConfig
from teg.value_stream.custom_instruction import parse_requested_count
from teg.value_stream.retrieval import retrieve
from teg.value_stream.selection import select_value_streams


# Each candidate-structure gets its own selection prompt (merge = lane-aware/historical-in-blocks;
# plain = pure VS list; evidence = pure VS list + a similar-past-tickets evidence block).
_PROMPT_BY_MODE = {
    "merge": "value_stream/selection",
    "historic_only": "value_stream/selection",  # candidates carry historical fields
    "all50": "value_stream/selection_plain",
    "topk": "value_stream/selection_plain",
    "evidence": "value_stream/selection_evidence",
}


@dataclass(frozen=True)
class PredictionTrace:
    """What survived each stage, for eval miss-bucketing (not part of the API contract)."""

    retrieved_ids: list[str] = field(default_factory=list)  # all merged candidate ids
    review_pool: list = field(default_factory=list)  # ValueStreamCandidate objects the LLM saw

    @property
    def review_pool_ids(self) -> list[str]:
        return [c.value_stream_id for c in self.review_pool]


class ValueStreamService:
    def __init__(
        self,
        search_client: SearchClient,
        llm_client: LLMClient,
        *,
        model_name: str = "",
        config: ValueStreamConfig = ValueStreamConfig(),
        base_rates: dict[str, float] | None = None,
        vs_details: dict[str, dict] | None = None,
    ) -> None:
        self._search = search_client
        self._llm = llm_client
        self._model_name = model_name
        self._config = config
        # Corpus tag-frequency prior per VS (broad-stream penalty). Global default; the eval
        # passes a per-ticket leave-one-out override via predict_traced.
        self._base_rates = base_rates or {}
        # Per-VS selection context from the governed catalogue (the lean index carries only
        # id+name); used to enrich candidate blocks: {vs_id: {description, category, trigger,
        # valueProposition}}.
        self._vs_details = vs_details or {}

    async def predict(self, request: ValueStreamRequest) -> ValueStreamResponse:
        response, _ = await self._predict(request)
        return response

    async def predict_traced(
        self, request: ValueStreamRequest, *, base_rates: dict[str, float] | None = None
    ) -> tuple[ValueStreamResponse, PredictionTrace]:
        """Same as :meth:`predict` but returns what reached the LLM (eval diagnostics).

        ``base_rates`` overrides the global prior for this call (the eval uses it to pass a
        leave-one-out frequency that excludes the ticket under test).
        """
        return await self._predict(request, base_rates=base_rates)

    async def _predict(
        self, request: ValueStreamRequest, *, base_rates: dict[str, float] | None = None
    ) -> tuple[ValueStreamResponse, PredictionTrace]:
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
        mode = self._config.selection_mode
        # In all50/topk/evidence the historic lane is NOT merged into candidates (VS-only pool);
        # in merge it is; in historic_only the pool is built from the historic VS only.
        hist_for_pool = [] if mode in ("all50", "topk", "evidence") else evidence
        candidates = build_candidates(
            [] if mode == "historic_only" else result.value_stream_hits,
            evidence if mode == "historic_only" else hist_for_pool,
            max_supporting_tickets=policy.max_supporting_tickets,
            base_rates=base_rates if base_rates is not None else self._base_rates,
            vs_details=self._vs_details,
        )
        review_pool = select_review_pool(candidates, policy=policy)
        # evidence mode: historic tickets shown as a context block, not merged.
        historic_evidence = _render_evidence(historical_hits) if mode == "evidence" else ""
        recommendations = await select_value_streams(
            query=request.summary_fields.generated_summary,
            candidates=review_pool,
            requested_count=requested_count,
            llm_client=self._llm,
            min_confidence=self._config.min_confidence,
            historic_evidence=historic_evidence,
            prompt_name=self._config.selection_prompt_override
            or _PROMPT_BY_MODE.get(mode, "value_stream/selection"),
        )
        response = ValueStreamResponse(
            ticket_id=request.ticket_id,
            recommendations=recommendations,
            historical_tickets=[_to_ticket(hit) for hit in historical_hits],
            model=self._model_name,
        )
        trace = PredictionTrace(
            retrieved_ids=[c.value_stream_id for c in candidates],
            review_pool=review_pool,
        )
        return response, trace

    async def aclose(self) -> None:
        """Close the search client's aio sessions (call when done; e.g. scripts)."""
        close = getattr(self._search, "close", None)
        if close is not None:
            await close()


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


def _render_evidence(hits: list[HistoricalHit]) -> str:
    """Render the similar past tickets as an evidence block (summary + the VS they were tagged
    with) for the 'evidence' selection mode - context the LLM weighs when picking from all VS."""
    lines: list[str] = []
    for hit in hits:
        vs = ", ".join(f"{v.value_stream_name} ({v.value_stream_id})" for v in hit.value_streams)
        snippet = (hit.snippet or "").strip().replace("\n", " ")[:200]
        lines.append(f"- {hit.ticket_id}: {snippet}\n  -> tagged value streams: {vs or '(none)'}")
    return "\n".join(lines)
