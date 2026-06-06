"""Contract C - Theme generation. Backend -> us, after HITL approves the VS set.

Backend replays the stored condensed data + the approved VS set. Governed stage /
L2 / L3 catalogues are read by us from Cosmos and are never sent by the backend.
We return one theme package per approved Value Stream.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from teg.domain.condensed import GenerationSignals, SummaryFields


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CondensedContextDTO(_Camel):
    summary_fields: SummaryFields
    generation_signals: GenerationSignals


class ApprovedValueStreamDTO(_Camel):
    value_stream_id: str
    value_stream_name: str


class ThemeGenerationRequest(_Camel):
    ticket_id: str
    ticket_title: str
    condensed: CondensedContextDTO
    approved_value_streams: list[ApprovedValueStreamDTO]


class ThemeDescriptionDTO(_Camel):
    theme_overview: str
    initiative_overview: str
    key_features: list[str] = Field(default_factory=list)
    product_availability: str | None = None
    digital_experience: str | None = None
    integration_operational_capabilities: str | None = None


class SelectedStageDTO(_Camel):
    stage_id: str
    stage_name: str
    rank: int
    reason: str
    evidence: str
    validation_status: str = "unknown"


class BusinessProductFeatureDTO(_Camel):
    feature_name: str
    needs: list[str] = Field(default_factory=list)
    notes: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)


class BusinessNeedDTO(_Camel):
    stage_id: str
    stage_name: str
    business_product_features: list[BusinessProductFeatureDTO] = Field(default_factory=list)
    operational_training: str | None = None
    operational_reporting: str | None = None
    validation_status: str = "unknown"


class CapabilityDTO(_Camel):
    name: str
    description: str
    reason: str


class StageCapabilitiesDTO(_Camel):
    stage_id: str
    stage_name: str
    capabilities: list[CapabilityDTO] = Field(default_factory=list)


class ThemePackageDTO(_Camel):
    value_stream_id: str
    value_stream_name: str
    theme_title: str
    theme_description: ThemeDescriptionDTO
    selected_stages: list[SelectedStageDTO] = Field(default_factory=list)
    business_needs: list[BusinessNeedDTO] = Field(default_factory=list)
    l2_capabilities: list[StageCapabilitiesDTO] = Field(default_factory=list)
    l3_capabilities: list[StageCapabilitiesDTO] = Field(default_factory=list)
    validation_status: str = "recommendation"


class ThemeGenerationResponse(_Camel):
    ticket_id: str
    theme_packages: list[ThemePackageDTO]
    model: str
    prompt_version: str
    latency_ms: int = 0
