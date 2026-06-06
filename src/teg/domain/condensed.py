"""Condensed ticket records (TDD 5.1-5.2).

The condense step is one LLM pass over the idea-card source material. It returns
``summaryFields`` (retrieval + routing + LLM context) and ``generationSignals``
(evidence for Theme Description and Business Needs). The output is shared by every
downstream generation step, so it is the single source of truth for ticket context.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Evidence:
    """One lightweight evidence item inside a generation signal.

    ``text`` is the supporting phrase, ``source`` is where it came from (e.g. the
    idea card or an attachment), ``source_section`` narrows it further when known.
    Signals are never invented: an absent category is an empty list, not a guess.
    """

    text: str
    source: str
    source_section: str | None = None


@dataclass
class SummaryFields:
    """Retrieval + routing + LLM context. Used by every downstream call."""

    generated_summary: str
    business_problem: str
    business_capability: str
    key_terms: list[str] = field(default_factory=list)
    stakeholders: list[str] = field(default_factory=list)
    systems_and_products: list[str] = field(default_factory=list)


@dataclass
class GenerationSignals:
    """Evidence arrays for Theme Description + Business Needs. Empty when absent."""

    market_segments: list[Evidence] = field(default_factory=list)
    funding_model_signals: list[Evidence] = field(default_factory=list)
    market_opportunity: list[Evidence] = field(default_factory=list)
    business_solution_objectives: list[Evidence] = field(default_factory=list)
    value_proposition: list[Evidence] = field(default_factory=list)
    estimated_benefits: list[Evidence] = field(default_factory=list)
    dependencies: list[Evidence] = field(default_factory=list)
    resources_needed: list[Evidence] = field(default_factory=list)
    digital_experience_signals: list[Evidence] = field(default_factory=list)
    product_availability_signals: list[Evidence] = field(default_factory=list)
    plan_signals: list[Evidence] = field(default_factory=list)
    network_signals: list[Evidence] = field(default_factory=list)
    product_pairing_signals: list[Evidence] = field(default_factory=list)
    business_rules: list[Evidence] = field(default_factory=list)
    operational_signals: list[Evidence] = field(default_factory=list)
    reporting_signals: list[Evidence] = field(default_factory=list)
    training_signals: list[Evidence] = field(default_factory=list)
    notes: list[Evidence] = field(default_factory=list)


@dataclass
class NormalizedContext:
    """The raw-ish context both source paths converge on."""

    description: str
    raw_text: str


@dataclass
class CondensedTicket:
    """Full condense output. The backend stores this and replays it downstream."""

    ticket_id: str
    ticket_title: str
    primary_source: str  # "idea_card" | "description_fallback"
    attachments_used: list[str]
    summary_fields: SummaryFields
    generation_signals: GenerationSignals
    normalized_context: NormalizedContext
