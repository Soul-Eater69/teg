"""Condensed ticket records (TDD 5.1-5.2).

The condense step is one LLM pass over the idea-card source material. It returns
``summary_fields`` (retrieval + routing + LLM context) and ``generation_signals``
(evidence for Theme Description and Business Needs). This output is shared by every
downstream step, so these models are the single source of truth - used internally
and serialized directly at the backend boundary (camelCase via CamelModel).
"""

from __future__ import annotations

from pydantic import Field

from teg.domain.base import CamelModel


class Evidence(CamelModel):
    """One lightweight evidence item inside a generation signal.

    Signals are never invented: an absent category is an empty list, not a guess.
    """

    text: str
    source: str
    source_section: str | None = None


class SummaryFields(CamelModel):
    """Retrieval + routing + LLM context. Used by every downstream call."""

    generated_summary: str
    business_problem: str
    business_capability: str
    key_terms: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    systems_and_products: list[str] = Field(default_factory=list)


class GenerationSignals(CamelModel):
    """Evidence arrays for Theme Description + Business Needs. Empty when absent."""

    market_segments: list[Evidence] = Field(default_factory=list)
    funding_model_signals: list[Evidence] = Field(default_factory=list)
    market_opportunity: list[Evidence] = Field(default_factory=list)
    business_solution_objectives: list[Evidence] = Field(default_factory=list)
    value_proposition: list[Evidence] = Field(default_factory=list)
    estimated_benefits: list[Evidence] = Field(default_factory=list)
    dependencies: list[Evidence] = Field(default_factory=list)
    resources_needed: list[Evidence] = Field(default_factory=list)
    digital_experience_signals: list[Evidence] = Field(default_factory=list)
    product_availability_signals: list[Evidence] = Field(default_factory=list)
    plan_signals: list[Evidence] = Field(default_factory=list)
    network_signals: list[Evidence] = Field(default_factory=list)
    product_pairing_signals: list[Evidence] = Field(default_factory=list)
    business_rules: list[Evidence] = Field(default_factory=list)
    operational_signals: list[Evidence] = Field(default_factory=list)
    reporting_signals: list[Evidence] = Field(default_factory=list)
    training_signals: list[Evidence] = Field(default_factory=list)
    notes: list[Evidence] = Field(default_factory=list)


class CondensedTicket(CamelModel):
    """Full condense output. The backend stores this and replays it downstream."""

    ticket_id: str
    ticket_title: str
    primary_source: str  # "idea_card" | "attachments_fallback"
    attachments_used: list[str] = Field(default_factory=list)
    summary_fields: SummaryFields
    generation_signals: GenerationSignals
    description: str
    raw_text: str  # consolidated description + extracted attachment text
