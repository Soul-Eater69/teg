"""Contract A - Condense. Backend -> us; backend stores the response.

These pydantic models are the wire contract. JSON is camelCase; Python is
snake_case (populate_by_name lets either work). Generate the JSON Schema for the
backend with ``CondenseResponse.model_json_schema(by_alias=True)``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class EvidenceDTO(_Camel):
    text: str
    source: str
    source_section: str | None = None


class SummaryFieldsDTO(_Camel):
    generated_summary: str
    business_problem: str
    business_capability: str
    key_terms: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    systems_and_products: list[str] = Field(default_factory=list)


class GenerationSignalsDTO(_Camel):
    market_segments: list[EvidenceDTO] = Field(default_factory=list)
    funding_model_signals: list[EvidenceDTO] = Field(default_factory=list)
    market_opportunity: list[EvidenceDTO] = Field(default_factory=list)
    business_solution_objectives: list[EvidenceDTO] = Field(default_factory=list)
    value_proposition: list[EvidenceDTO] = Field(default_factory=list)
    estimated_benefits: list[EvidenceDTO] = Field(default_factory=list)
    dependencies: list[EvidenceDTO] = Field(default_factory=list)
    resources_needed: list[EvidenceDTO] = Field(default_factory=list)
    digital_experience_signals: list[EvidenceDTO] = Field(default_factory=list)
    product_availability_signals: list[EvidenceDTO] = Field(default_factory=list)
    plan_signals: list[EvidenceDTO] = Field(default_factory=list)
    network_signals: list[EvidenceDTO] = Field(default_factory=list)
    product_pairing_signals: list[EvidenceDTO] = Field(default_factory=list)
    business_rules: list[EvidenceDTO] = Field(default_factory=list)
    operational_signals: list[EvidenceDTO] = Field(default_factory=list)
    reporting_signals: list[EvidenceDTO] = Field(default_factory=list)
    training_signals: list[EvidenceDTO] = Field(default_factory=list)
    notes: list[EvidenceDTO] = Field(default_factory=list)


class CondenseOptions(_Camel):
    extraction_backend: str = "auto"  # auto | current | unstructured
    max_attachments: int = 4


class CondenseRequest(_Camel):
    ticket_id: str | None = None  # required unless idea_card_text is given
    idea_card_text: str | None = None  # optional override; skips Jira fetch
    options: CondenseOptions = Field(default_factory=CondenseOptions)


class CondensedTicketDTO(_Camel):
    """The object the backend stores and replays into Contracts B and C."""

    ticket_id: str
    ticket_title: str
    primary_source: str  # idea_card | description_fallback
    attachments_used: list[str] = Field(default_factory=list)
    summary_fields: SummaryFieldsDTO
    generation_signals: GenerationSignalsDTO
    description: str
    raw_text: str


class CondenseResponse(_Camel):
    condensed: CondensedTicketDTO
    model: str
    prompt_version: str
