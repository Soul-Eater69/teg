"""Theme package records (TDD 6.2-6.3).

One ThemePackage is produced per approved Value Stream. It stays a recommendation
until the SME approves it for Jira writeback (HITL is owned by the backend).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .stage import SelectedStage, ValidationStatus


@dataclass
class ThemeDescription:
    """Structured Theme description. Optional sections are None when not generated."""

    theme_overview: str
    initiative_overview: str
    key_features: list[str] = field(default_factory=list)
    product_availability: str | None = None
    digital_experience: str | None = None
    integration_operational_capabilities: str | None = None


@dataclass
class BusinessProductFeature:
    feature_name: str
    needs: list[str] = field(default_factory=list)
    notes: str | None = None
    dependencies: list[str] = field(default_factory=list)
    business_rules: list[str] = field(default_factory=list)


@dataclass
class BusinessNeed:
    """Per-stage business needs for the Theme."""

    stage_id: str
    stage_name: str
    business_product_features: list[BusinessProductFeature] = field(default_factory=list)
    operational_training: str | None = None
    operational_reporting: str | None = None
    validation_status: ValidationStatus = "unknown"


@dataclass
class Capability:
    """An L2 or L3 capability."""

    name: str
    description: str
    reason: str


@dataclass
class StageCapabilities:
    """Capabilities grouped under one selected stage."""

    stage_id: str
    stage_name: str
    capabilities: list[Capability] = field(default_factory=list)


@dataclass
class ThemePackage:
    """Everything generated for one approved Value Stream."""

    value_stream_id: str
    value_stream_name: str
    theme_title: str  # deterministic: "<ticket title> - <value stream name>"
    theme_description: ThemeDescription
    selected_stages: list[SelectedStage] = field(default_factory=list)
    business_needs: list[BusinessNeed] = field(default_factory=list)
    l2_capabilities: list[StageCapabilities] = field(default_factory=list)
    l3_capabilities: list[StageCapabilities] = field(default_factory=list)
    validation_status: str = "recommendation"
