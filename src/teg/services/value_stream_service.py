"""Value Stream prediction service facade (Contract B).

The backend calls :meth:`ValueStreamService.predict`. Retrieval, merge, and the
review-pool LLM selection live under teg.value_stream and are injected here.
"""

from __future__ import annotations

from teg.contracts.value_stream_io import ValueStreamRequest, ValueStreamResponse


class ValueStreamService:
    def __init__(self, search_client, llm_client) -> None:
        self._search = search_client
        self._llm = llm_client

    async def predict(self, request: ValueStreamRequest) -> ValueStreamResponse:
        """Two retrieval lanes -> merge/rank -> review-pool LLM selection.

        Flow (TDD 5.3-5.5):
          1. parallel lanes vs idp_idmt_data: VS catalogue (top 50) + historical ER (top 6).
          2. merge into buckets (semantic+historic / historic-only / semantic-only),
             apply caps + gates + generic/risky penalty.
          3. two parallel review-pool LLM calls -> merge/dedupe/validate vs approved catalogue.

        TODO: implement via teg.value_stream.{retrieval,candidate_merger,review_pool,selection}.
        Backlog: B3 (lanes), B5 (two-call split), B6 (valueStreamId resolution).
        """
        raise NotImplementedError
