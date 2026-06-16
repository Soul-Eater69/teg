"""Theme Description generation, split into a shared body + per-VS framing.

An idea's theme description is mostly ticket-level (product availability, the initiative
overview, digital/operational capabilities) - identical for every approved value stream. So
the body is generated ONCE per ticket, and a single batched call produces the VS-specific
opening paragraph for every value stream. The final per-VS description is framing + body. This
replaces N separate full-description calls with 2 calls total. Returns text strings.
"""

from __future__ import annotations

from pydantic import Field

from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.base import CamelModel
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt
from teg.theme.context import render_ticket_context



class _GeneratedDescription(CamelModel):
    """LLM structured output: a consolidated theme-description text block."""

    text: str


class _VsFraming(CamelModel):
    value_stream_id: str
    text: str = ""


class _VsFramings(CamelModel):
    """Batched output: one opening paragraph per approved value stream."""

    framings: list[_VsFraming] = Field(default_factory=list)


async def generate_description_body(
    *, condensed: CondensedContext, llm_client: LLMClient
) -> str:
    """The shared, VS-agnostic body (availability + initiative + capabilities). One call."""
    prompt = load_prompt("theme/description_body")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
    )
    result = await llm_client.complete(system=system, user=user, schema=_GeneratedDescription)
    return result.text


async def generate_vs_framings(
    *,
    condensed: CondensedContext,
    approved_value_streams: list[ApprovedValueStream],
    value_stream_details: dict[str, tuple[str, str]],  # vs_id -> (description, value_proposition)
    llm_client: LLMClient,
) -> dict[str, str]:
    """The VS-specific opening paragraph for every value stream, in one batched call.

    Returns {value_stream_id: framing_text}; a value stream the model omits gets "".
    """
    if not approved_value_streams:
        return {}
    blocks = []
    for vs in approved_value_streams:
        desc, prop = value_stream_details.get(vs.value_stream_id, ("", ""))
        block = [
            f"- valueStreamId: {vs.value_stream_id}",
            f"  valueStreamName: {vs.value_stream_name}",
        ]
        if desc:
            block.append(f"  valueStreamDescription: {desc}")
        if prop:
            block.append(f"  valueProposition: {prop}")
        blocks.append("\n".join(block))

    prompt = load_prompt("theme/description_framing")
    system, user = prompt.render(
        ticket_context=render_ticket_context(condensed),
        value_streams="\n".join(blocks),
    )
    result = await llm_client.complete(system=system, user=user, schema=_VsFramings)
    return {f.value_stream_id: f.text for f in result.framings if f.value_stream_id}


def assemble_description(framing: str, body: str) -> str:
    """Final per-VS theme description: a 'Theme Description:' heading over the VS framing
    paragraph, then the shared body (which opens with its own Product Availability heading)."""
    parts: list[str] = []
    if framing and framing.strip():
        parts.append("Theme Description:\n" + framing.strip())
    if body and body.strip():
        parts.append(body.strip())
    return "\n\n".join(parts)
