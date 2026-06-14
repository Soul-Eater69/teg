"""Native ragas-style LLM judges for generated theme descriptions (eval-only, REFERENCE-FREE).

We do NOT score against the ground-truth description: each GT is free-form with its own format, so
statement-matching it would penalise style, not substance. Instead we judge ONLY against the passed
SOURCE (the idea card / ticket) - the ragas methodology (claim decomposition + grounding) without
the dependency:
  - faithfulness : decompose the description into atomic claims, mark each supported by the SOURCE.
                   score = supported / total. (This is also 'correctness' when reference-free - a
                   claim is correct iff the source supports it.)
  - hallucination: 1 - faithfulness (the unsupported claims, listed - the 'why').
  - coverage     : extract the source's key facts, mark each covered by the description.
                   score = covered / total (did it omit important ticket content?).
All run post-hoc, never feed into generation, and surface the offending claims/facts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from teg.domain.base import CamelModel
from teg.integrations.llm import LLMClient


# --------------------------------------------------------------------------- #
# Faithfulness / hallucination - claims grounded in the source
# --------------------------------------------------------------------------- #

class Claim(CamelModel):
    claim: str
    supported: bool = False  # is this claim supported by the SOURCE text?


class FaithfulnessResult(CamelModel):
    claims: list[Claim] = Field(default_factory=list)

    def score(self) -> float:
        """Faithfulness = supported claims / total claims (1.0 when there are no claims)."""
        return sum(1 for c in self.claims if c.supported) / len(self.claims) if self.claims else 1.0

    def unsupported(self) -> list[str]:
        return [c.claim for c in self.claims if not c.supported]


_FAITHFULNESS_SYSTEM = (
    "You verify a generated business description against its SOURCE. Break the description into "
    "atomic factual claims (one self-contained fact each). For EACH claim, decide whether it is "
    "supported by the source - i.e. the source states or directly implies it. A claim invented, "
    "assumed, or not derivable from the source is NOT supported. Judge only against the source; do "
    "not use outside knowledge. Return every claim with its supported flag."
)


async def judge_faithfulness(
    *, description: str, source: str, llm_client: LLMClient
) -> FaithfulnessResult:
    """Decompose the description into claims and mark each as supported by the source."""
    if not description.strip():
        return FaithfulnessResult()
    user = f"SOURCE:\n{source}\n\nGENERATED DESCRIPTION:\n{description}\n\nList every claim with its supported flag."
    return await llm_client.complete(
        system=_FAITHFULNESS_SYSTEM, user=user, schema=FaithfulnessResult)


# --------------------------------------------------------------------------- #
# Coverage - does the description capture the source's key facts? (reference-free completeness)
# --------------------------------------------------------------------------- #

class SourceFact(CamelModel):
    fact: str
    covered: bool = False  # is this source fact reflected in the description?


class CoverageResult(CamelModel):
    facts: list[SourceFact] = Field(default_factory=list)

    def score(self) -> float:
        """Coverage = covered key facts / total key facts (1.0 when the source has no key facts)."""
        return sum(1 for f in self.facts if f.covered) / len(self.facts) if self.facts else 1.0

    def missed(self) -> list[str]:
        return [f.fact for f in self.facts if not f.covered]


_COVERAGE_SYSTEM = (
    "You check whether a generated business description covers the important content of its SOURCE. "
    "Extract the KEY facts a theme description for this work should convey from the source (the "
    "business change, who/what it affects, the core capability/outcome - not trivia). For EACH key "
    "fact, decide whether the generated description reflects it. Judge coverage by meaning, not "
    "wording. Return every key fact with its covered flag."
)


async def judge_coverage(
    *, description: str, source: str, llm_client: LLMClient
) -> CoverageResult:
    """Extract the source's key facts and mark each as covered by the description."""
    if not source.strip():
        return CoverageResult()
    user = (f"SOURCE:\n{source}\n\nGENERATED DESCRIPTION:\n{description}\n\n"
            f"List the source's key facts, each with whether the description covers it.")
    return await llm_client.complete(
        system=_COVERAGE_SYSTEM, user=user, schema=CoverageResult)
