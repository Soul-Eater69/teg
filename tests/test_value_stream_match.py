"""Theme -> VS resolution: clean summary + 3-tier match (exact / fuzzy / LLM verifier)."""

from __future__ import annotations

from teg.ingestion.catalogues.models import CatalogueValueStream
from teg.ingestion.ground_truth.value_stream_match import (
    VsVerification,
    VsVerificationItem,
    ValueStreamResolver,
    clean_value_stream_name,
)


def _vs(vs_id: str, name: str) -> CatalogueValueStream:
    return CatalogueValueStream(
        value_stream_id=vs_id,
        value_stream_name=name,
        value_stream_description="",
        value_proposition="",
        trigger="",
        category="",
        assumptions="",
        defined_terms="",
        active=True,
        created_date="",
        created_by="",
        modified_date="",
        modified_by="",
    )


CATALOGUE = [_vs("VSR1", "Resolve Appeal"), _vs("VSR2", "Adjudicate Claim")]


class FakeLLM:
    def __init__(self, verification: VsVerification) -> None:
        self._verification = verification
        self.called = False

    async def complete(self, *, system, user, schema):
        self.called = True
        return self._verification


def test_clean_strips_prefix_and_takes_tail() -> None:
    assert clean_value_stream_name("CP 2027 Guided Health Plans : Resolve Appeal") == "Resolve Appeal"
    assert clean_value_stream_name("GROUP-12: Adjudicate Claim") == "Adjudicate Claim"


async def test_exact_match_skips_llm() -> None:
    resolver = ValueStreamResolver(CATALOGUE)
    fake = FakeLLM(VsVerification())
    out = await resolver.resolve(["CP 2027 Plans : Resolve Appeal"], fake)
    assert out["CP 2027 Plans : Resolve Appeal"] == ("VSR1", "Resolve Appeal")
    assert fake.called is False  # exact (normalized) match, no verifier call


async def test_fuzzy_match_skips_llm() -> None:
    resolver = ValueStreamResolver(CATALOGUE)
    fake = FakeLLM(VsVerification())
    out = await resolver.resolve(["Plans : Adjudicate Claims"], fake)  # plural typo
    assert out["Plans : Adjudicate Claims"] == ("VSR2", "Adjudicate Claim")
    assert fake.called is False


async def test_llm_verifier_resolves_alias() -> None:
    resolver = ValueStreamResolver(CATALOGUE)
    fake = FakeLLM(
        VsVerification(mappings=[VsVerificationItem(raw_name="Appeals Handling", approved_value_stream="Resolve Appeal")])
    )
    out = await resolver.resolve(["Health Plan - Appeals Handling"], fake)
    assert out["Health Plan - Appeals Handling"] == ("VSR1", "Resolve Appeal")
    assert fake.called is True


async def test_unmatched_is_dropped() -> None:
    resolver = ValueStreamResolver(CATALOGUE)
    fake = FakeLLM(VsVerification(mappings=[VsVerificationItem(raw_name="Totally Unrelated", approved_value_stream=None)]))
    out = await resolver.resolve(["Plan - Totally Unrelated"], fake)
    assert out["Plan - Totally Unrelated"] is None  # no approved VS -> dropped
