"""Candidate-block rendering (T7) + selection LLM resolution (T8)."""

from __future__ import annotations

from teg.value_stream.candidate_blocks import render_candidate_blocks
from teg.value_stream.models import ValueStreamCandidate
from teg.value_stream.selection import select_value_streams


class _FakeLLM:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def complete(self, *, system, user, schema):
        return schema.model_validate(self._payload)


def _cand(vs_id, lane, *, name=None, source_ticket_ids=None):
    return ValueStreamCandidate(
        value_stream_id=vs_id,
        value_stream_name=name or vs_id,
        lane=lane,
        source_ticket_ids=source_ticket_ids or [],
    )


# ---- T7: candidate block rendering ---------------------------------------

def test_render_includes_entity_id_lane_and_historical() -> None:
    candidate = ValueStreamCandidate(
        value_stream_id="VS1",
        value_stream_name="Adjudicate Claim",
        from_semantic=True,
        from_historical=True,
        semantic_score=1.4,
        semantic_rank=1,
        supporting_ticket_count=2,
        direct_count=1,
        implied_count=1,
        best_support_score=0.82,
        source_ticket_ids=["IDMT-1"],
        evidence=["claims savings"],
        lane="semantic_plus_historic",
    )
    block = render_candidate_blocks([candidate])
    assert "entity_id: VS1" in block
    assert "lane: semantic_plus_historic" in block
    assert "historical: tickets=2" in block
    assert "evidence: claims savings" in block


def test_render_includes_rich_vs_context() -> None:
    candidate = ValueStreamCandidate(
        value_stream_id="VS1",
        value_stream_name="Acquire Asset",
        value_stream_description="request to delivery",
        category="Finance",
        trigger="Asset Requester",
        value_proposition="faster asset turnaround",
        from_semantic=True,
        lane="semantic_only",
    )
    block = render_candidate_blocks([candidate])
    assert "category: Finance" in block
    assert "trigger: Asset Requester" in block
    assert "value: faster asset turnaround" in block
    assert "stakeholders" not in block  # stakeholders deliberately not fed to selection


def test_render_omits_rich_context_when_absent() -> None:
    # A historic-only candidate has no catalogue details - those lines are omitted.
    block = render_candidate_blocks([_cand("VS3", "historic_only", name="Issue Payment")])
    assert "category:" not in block and "trigger:" not in block and "value:" not in block


def test_render_semantic_only_omits_historical() -> None:
    block = render_candidate_blocks([_cand("VS2", "semantic_only", name="Receive Care")])
    assert "lane: semantic_only" in block
    assert "historical:" not in block


# ---- T8: selection resolution --------------------------------------------

async def test_selection_resolves_scales_confidence_and_source_tickets() -> None:
    candidates = [
        _cand("VS1", "semantic_plus_historic", name="Adjudicate Claim", source_ticket_ids=["IDMT-1"]),
        _cand("VS2", "semantic_only", name="Issue Payment"),
    ]
    payload = {
        "picks": [
            {"entityId": "VS1", "confidence": 0.82, "supportType": "implied", "reason": "claims"},
            {"entityId": "VS2", "confidence": 0.5, "supportType": "implied", "reason": "billing"},
        ]
    }
    recs = await select_value_streams(
        query="q", candidates=candidates, requested_count=2, llm_client=_FakeLLM(payload)
    )
    assert [r.value_stream_id for r in recs] == ["VS1", "VS2"]
    assert recs[0].confidence == 82.0  # 0.82 -> 82
    assert recs[0].source_tickets == ["IDMT-1"]  # implied + historic-backed -> shown
    assert recs[1].source_tickets == []  # implied but semantic_only -> no tickets to show


async def test_direct_pick_hides_source_tickets() -> None:
    # A direct pick is explicitly named, so its historic backing is not surfaced.
    candidates = [_cand("VS1", "semantic_plus_historic", name="Adjudicate Claim", source_ticket_ids=["IDMT-1"])]
    payload = {"picks": [{"entityId": "VS1", "confidence": 0.9, "supportType": "direct", "reason": "claims"}]}
    recs = await select_value_streams(
        query="q", candidates=candidates, requested_count=1, llm_client=_FakeLLM(payload)
    )
    assert recs[0].support_type == "direct"
    assert recs[0].source_tickets == []  # direct -> hidden even though historic-backed


async def test_selection_ignores_unknown_ids_and_dedupes() -> None:
    candidates = [_cand("VS1", "semantic_only")]
    payload = {
        "picks": [
            {"entityId": "VS1", "confidence": 0.9, "supportType": "direct", "reason": "a"},
            {"entityId": "VS1", "confidence": 0.9, "supportType": "direct", "reason": "dup"},
            {"entityId": "GHOST", "confidence": 0.9, "supportType": "direct", "reason": "x"},
        ]
    }
    recs = await select_value_streams(
        query="q", candidates=candidates, requested_count=5, llm_client=_FakeLLM(payload)
    )
    assert [r.value_stream_id for r in recs] == ["VS1"]  # ghost dropped, dup deduped


async def test_enforce_count_trims_and_pads() -> None:
    candidates = [_cand(f"VS{i}", "semantic_only") for i in range(3)]
    trim = await select_value_streams(
        query="q",
        candidates=candidates,
        requested_count=2,
        llm_client=_FakeLLM({"picks": [{"entityId": f"VS{i}", "confidence": 0.8} for i in range(3)]}),
    )
    assert len(trim) == 2

    pad = await select_value_streams(
        query="q",
        candidates=candidates,
        requested_count=3,
        llm_client=_FakeLLM({"picks": [{"entityId": "VS0", "confidence": 0.8, "supportType": "direct"}]}),
    )
    assert [r.value_stream_id for r in pad] == ["VS0", "VS1", "VS2"]
    assert pad[1].confidence == 30.0  # filled at the confidence floor


async def test_abstention_keeps_only_confident_picks_and_does_not_pad() -> None:
    candidates = [_cand(f"VS{i}", "semantic_only") for i in range(4)]
    # LLM emits 3 picks but only 2 clear the 0.45 floor; with min_confidence the weak one is
    # dropped and the count is NOT padded back up.
    recs = await select_value_streams(
        query="q",
        candidates=candidates,
        requested_count=4,
        min_confidence=0.45,
        llm_client=_FakeLLM({"picks": [
            {"entityId": "VS0", "confidence": 0.9},
            {"entityId": "VS1", "confidence": 0.5},
            {"entityId": "VS2", "confidence": 0.3},  # below floor
        ]}),
    )
    assert [r.value_stream_id for r in recs] == ["VS0", "VS1"]  # VS2 dropped, no padding to 4


async def test_abstention_caps_at_requested_count() -> None:
    candidates = [_cand(f"VS{i}", "semantic_only") for i in range(5)]
    recs = await select_value_streams(
        query="q",
        candidates=candidates,
        requested_count=2,
        min_confidence=0.4,
        llm_client=_FakeLLM({"picks": [{"entityId": f"VS{i}", "confidence": 0.9} for i in range(5)]}),
    )
    assert len(recs) == 2  # count is still an upper bound
