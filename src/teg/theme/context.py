"""Render the condensed context into the factual text the theme prompts read.

The condensed context is the ONLY factual source. Summary fields and generation signals are
rendered separately so each prompt can include the slice it needs (theme description uses the
product-availability signals; stage selection uses the operational ones). Historic
theme/stage context is deliberately excluded.
"""

from __future__ import annotations

from teg.contracts.theme_io import CondensedContextDTO


def render_ticket_context(condensed: CondensedContextDTO) -> str:
    sf = condensed.summary_fields
    lines: list[str] = []
    if sf.generated_summary:
        lines.append(f"- generatedSummary: {sf.generated_summary}")
    if sf.business_problem:
        lines.append(f"- businessProblem: {sf.business_problem}")
    if sf.business_capability:
        lines.append(f"- businessCapability: {sf.business_capability}")
    if sf.key_terms:
        lines.append(f"- keyTerms: {', '.join(sf.key_terms)}")
    if sf.stakeholders:
        lines.append(f"- stakeholders: {', '.join(sf.stakeholders)}")
    if sf.systems_and_products:
        lines.append(f"- systemsAndProducts: {', '.join(sf.systems_and_products)}")
    return "\n".join(lines)


def render_generation_signals(condensed: CondensedContextDTO, fields: list[str]) -> str:
    """Render the named generation-signal fields that are populated (camelCase labels)."""
    data = condensed.generation_signals.model_dump(by_alias=True)
    lines = [f"- {name}: {'; '.join(data[name])}" for name in fields if data.get(name)]
    return "\n".join(lines) if lines else "- (none provided)"
