"""VS support classification (direct/implied historic GT) with a fake LLM."""

from __future__ import annotations

from teg.ingestion.ground_truth.value_stream_classification import (
    VsClassification,
    VsClassificationItem,
    classify_value_streams,
)


class FakeLLM:
    def __init__(self, result: VsClassification) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str, schema):
        self.calls.append((system, user))
        return self._result


async def test_labels_each_vs_direct_or_implied() -> None:
    result = VsClassification(
        value_streams=[
            VsClassificationItem(vs_name="Adjudicate Claim", inference_type="direct", reason="claims adjudication is central", evidence="automate claims adjudication"),
            VsClassificationItem(vs_name="Configure, Price, and Quote", inference_type="implied", reason="adjacent quoting step"),
        ]
    )
    out = await classify_value_streams(
        ticket_id="IDMT-1",
        text="[DESCRIPTION] claims adjudication automation",
        value_stream_names=["Adjudicate Claim", "Configure, Price, and Quote"],
        llm_client=FakeLLM(result),
    )
    assert out["Adjudicate Claim"].inference_type == "direct"
    assert "claims" in out["Adjudicate Claim"].reason
    assert out["Adjudicate Claim"].evidence == "automate claims adjudication"
    assert out["Configure, Price, and Quote"].inference_type == "implied"


async def test_omitted_vs_defaults_to_implied() -> None:
    result = VsClassification(
        value_streams=[VsClassificationItem(vs_name="A", inference_type="direct", reason="x")]
    )
    out = await classify_value_streams(
        ticket_id="T", text="t", value_stream_names=["A", "B"], llm_client=FakeLLM(result)
    )
    assert out["A"].inference_type == "direct"
    assert out["B"].inference_type == "implied"  # model omitted B -> default


async def test_empty_names_skips_llm() -> None:
    fake = FakeLLM(VsClassification())
    out = await classify_value_streams(
        ticket_id="T", text="t", value_stream_names=[], llm_client=fake
    )
    assert out == {}
    assert fake.calls == []  # no LLM call when there's nothing to classify
