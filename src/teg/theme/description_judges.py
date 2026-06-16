"""Native ragas-style LLM judges for generated theme descriptions (eval-only, REFERENCE-FREE).

We do NOT score against the ground-truth description: each GT is free-form with its own format, so
statement-matching it would penalise style, not substance. We judge ONLY against the passed SOURCE
(the idea card / ticket). Claim decomposition is a SEPARATE call from the grounding judgements so the
claim set is extracted neutrally (not biased by the model grading its own extraction in one pass) and
reused across metrics:

  1. extract_claims : decompose the generated text into atomic factual claims (one call).
  2. faithfulness   : per claim, is it SUPPORTED by the source? score = supported / total.
     hallucination  : 1 - faithfulness (derived; the unsupported claims are the 'why').
  3. coverage       : extract the source's key facts, mark each covered (one call).
  4. correctness    : per claim, is it ACCURATELY stated per the source (right details, no
                      distortion/exaggeration)? score = correct / total - stricter than 'supported'.

All run post-hoc, never feed into generation, and surface the offending claims/facts.
"""

from __future__ import annotations

from pydantic import Field

from teg.domain.base import CamelModel
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt


def _claim_lines(claims: list[str]) -> str:
    return "\n".join(f"- {c}" for c in claims)


# --------------------------------------------------------------------------- #
# 1. Claim extraction - neutral atomic decomposition (its own call)
# --------------------------------------------------------------------------- #

class ClaimList(CamelModel):
    claims: list[str] = Field(default_factory=list)


async def extract_claims(*, text: str, llm_client: LLMClient) -> list[str]:
    """Decompose the generated text into atomic claims (no grounding judgement)."""
    if not text.strip():
        return []
    system, user = load_prompt("judges/claim_extraction").render(text=text)
    result = await llm_client.complete(system=system, user=user, schema=ClaimList)
    return [c for c in result.claims if c.strip()]


# --------------------------------------------------------------------------- #
# 2. Faithfulness / hallucination - are the extracted claims supported by the source
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


async def judge_faithfulness(
    *, claims: list[str], source: str, llm_client: LLMClient
) -> FaithfulnessResult:
    """Per pre-extracted claim: is it supported by the source? (faithfulness; hallucination = 1-it)."""
    if not claims:
        return FaithfulnessResult()
    system, user = load_prompt("judges/faithfulness").render(source=source, claims=_claim_lines(claims))
    return await llm_client.complete(system=system, user=user, schema=FaithfulnessResult)


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


async def judge_coverage(
    *, description: str, source: str, llm_client: LLMClient
) -> CoverageResult:
    """Extract the source's key facts and mark each as covered by the description."""
    if not source.strip():
        return CoverageResult()
    system, user = load_prompt("judges/coverage").render(source=source, description=description)
    return await llm_client.complete(system=system, user=user, schema=CoverageResult)


# --------------------------------------------------------------------------- #
# 4. Correctness - are the extracted claims ACCURATELY stated per the source
# --------------------------------------------------------------------------- #

class CorrectClaim(CamelModel):
    claim: str
    correct: bool = False  # accurately stated per the source (right details, no distortion)?


class CorrectnessResult(CamelModel):
    claims: list[CorrectClaim] = Field(default_factory=list)

    def score(self) -> float:
        """Correctness = correct claims / total claims (1.0 when there are no claims)."""
        return sum(1 for c in self.claims if c.correct) / len(self.claims) if self.claims else 1.0

    def incorrect(self) -> list[str]:
        return [c.claim for c in self.claims if not c.correct]


async def judge_correctness(
    *, claims: list[str], source: str, llm_client: LLMClient
) -> CorrectnessResult:
    """Per pre-extracted claim: is it an accurate, undistorted statement of the source?"""
    if not claims:
        return CorrectnessResult()
    system, user = load_prompt("judges/correctness").render(source=source, claims=_claim_lines(claims))
    return await llm_client.complete(system=system, user=user, schema=CorrectnessResult)
