"""Stage-usage judge for generated Business Needs (eval-only).

Business Needs are written as one 'Value Stage: <name>' block per selected stage. Beyond the
reference-free faithfulness / coverage judges (reused from description_judges), business needs has a
structural check: did the output USE every selected stage, and are each stage's needs ALIGNED to
that stage's scope (its catalogue description / entrance-exit), not misfiled under the wrong stage?

  stage usage     : selected stages addressed in the output / total selected
  stage alignment : addressed stages whose needs fit the stage's scope / addressed

One LLM call returns both per stage.
"""

from __future__ import annotations

from pydantic import Field

from teg.domain.base import CamelModel
from teg.ingestion.catalogues.models import CatalogueStage
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.theme.stage_catalogue import render_candidate_stages


class StageUsage(CamelModel):
    stage_id: str
    addressed: bool = False  # does the Business Needs have a block for this stage?
    aligned: bool = False  # are this stage's needs consistent with the stage's scope?
    note: str = ""


class StageUsageResult(CamelModel):
    stages: list[StageUsage] = Field(default_factory=list)

    def usage(self) -> float:
        """Selected stages addressed / total selected (1.0 when no stages)."""
        return sum(1 for s in self.stages if s.addressed) / len(self.stages) if self.stages else 1.0

    def alignment(self) -> float:
        """Of the ADDRESSED stages, how many have needs aligned to the stage scope (1.0 if none)."""
        addressed = [s for s in self.stages if s.addressed]
        return sum(1 for s in addressed if s.aligned) / len(addressed) if addressed else 1.0

    def unused(self) -> list[str]:
        return [s.stage_id for s in self.stages if not s.addressed]

    def misaligned(self) -> list[str]:
        return [s.stage_id for s in self.stages if s.addressed and not s.aligned]

    def misaligned_notes(self) -> list[str]:
        """'<stage_id>: <why it's misaligned>' for each addressed-but-not-aligned stage."""
        return [f"{s.stage_id}: {s.note}" for s in self.stages if s.addressed and not s.aligned]


async def judge_stage_usage(
    *, business_needs: str, stages: list[CatalogueStage], llm_client: LLMClient
) -> StageUsageResult:
    """Per selected stage: is it addressed in the Business Needs, and are its needs in-scope?"""
    if not stages or not business_needs.strip():
        return StageUsageResult()
    system, user = load_prompt("judges/stage_usage").render(
        stages=render_candidate_stages(stages), business_needs=business_needs)
    return await llm_client.complete(system=system, user=user, schema=StageUsageResult)
