"""Classify each Jira-linked Value Stream as direct or implied (historic ground truth).

This is support classification, not prediction: it never discovers new labels and never
invents names - it only labels the value streams already attached to the ticket, judged
against the consolidated ticket text. Output is the VsClassification pydantic model
(structured output). Every supplied name is always returned; ones the model omits default
to ``implied`` (the prompt's bias).
"""

from __future__ import annotations

from pydantic import Field

from teg.domain.base import CamelModel
from teg.domain.value_stream import SupportType
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt

# The consolidated ticket text can be large; cap what we send (matches the vs flow).
_INPUT_CHAR_LIMIT = 20_000


class VsClassificationItem(CamelModel):
    vs_name: str
    inference_type: SupportType = "implied"
    reason: str = ""
    evidence: str = ""  # short verbatim snippet from the ticket supporting the call


class VsClassification(CamelModel):
    """Structured output: one item per supplied value stream."""

    value_streams: list[VsClassificationItem] = Field(default_factory=list)


async def classify_value_streams(
    *,
    ticket_id: str,
    text: str,
    value_stream_names: list[str],
    llm_client: LLMClient,
) -> dict[str, VsClassificationItem]:
    """Return {value_stream_name: classification} for every supplied name."""
    names = [name.strip() for name in value_stream_names if name and name.strip()]
    if not names:
        return {}

    prompt = load_prompt("ingestion/value_stream_classification")
    system, user = prompt.render(
        ticket_id=ticket_id,
        text=text[:_INPUT_CHAR_LIMIT],
        value_streams="\n".join(f"- {name}" for name in names),
    )
    result = await llm_client.complete(system=system, user=user, schema=VsClassification)

    by_name = {item.vs_name.strip(): item for item in result.value_streams}
    return {
        name: by_name.get(name, VsClassificationItem(vs_name=name, inference_type="implied"))
        for name in names
    }
