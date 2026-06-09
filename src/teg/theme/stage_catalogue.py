"""Allowed-stage lookup for an approved Value Stream.

Stage generation needs the governed stages for a VS (point-read by valueStreamId). Until
the Cosmos catalogue read exists, this is built from the loaded Sightline catalogue (the
same source). Renders the candidate stages with the fields the selection prompt matches on
(description, entrance/exit criteria, value items, stakeholders).
"""

from __future__ import annotations

from dataclasses import dataclass

from teg.ingestion.catalogues.models import CatalogueStage, CatalogueValueStream


@dataclass(frozen=True)
class StageCatalogue:
    _by_value_stream: dict[str, CatalogueValueStream]

    @classmethod
    def from_catalogue(cls, catalogue: list[CatalogueValueStream]) -> "StageCatalogue":
        return cls({vs.value_stream_id: vs for vs in catalogue})

    def stages_for(self, value_stream_id: str) -> list[CatalogueStage]:
        vs = self._by_value_stream.get(value_stream_id)
        return list(vs.stages) if vs else []

    def description_for(self, value_stream_id: str) -> str:
        vs = self._by_value_stream.get(value_stream_id)
        return vs.value_stream_description if vs else ""


def render_candidate_stages(stages: list[CatalogueStage]) -> str:
    return "\n\n".join(_stage_block(s) for s in stages)


def _stage_block(s: CatalogueStage) -> str:
    lines = [f"[{s.sequence}] {s.stage_name} ({s.stage_id})"]
    if s.stage_description:
        lines.append(f"description: {s.stage_description}")
    if s.entrance_criteria or s.exit_criteria:
        lines.append(f"entrance: {s.entrance_criteria} | exit: {s.exit_criteria}")
    if s.value_items:
        lines.append(f"value: {s.value_items}")
    if s.stakeholders:
        lines.append(f"stakeholders: {', '.join(s.stakeholders)}")
    return "\n".join(lines)
