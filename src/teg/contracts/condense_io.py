"""Contract A - Condense. Backend -> us; backend stores the response.

The condensed records themselves live in ``teg.domain.condensed`` (single source of
truth) and serialize to camelCase JSON directly. This module only adds the request /
response envelope. Generate JSON Schema for the backend with
``CondenseResponse.model_json_schema(by_alias=True)``.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from teg.domain.base import CamelModel
from teg.domain.condensed import CondensedTicket  # re-exported for the boundary


class CondenseOptions(CamelModel):
    extraction_backend: str = "auto"  # auto | current | unstructured
    max_attachments: int = 4


class CondenseRequest(CamelModel):
    ticket_id: str | None = None  # required unless idea_card_text is given
    idea_card_text: str | None = None  # optional override; skips Jira fetch
    options: CondenseOptions = Field(default_factory=CondenseOptions)

    @model_validator(mode="after")
    def _require_some_input(self) -> "CondenseRequest":
        if not self.ticket_id and not self.idea_card_text:
            raise ValueError("ticket_id or idea_card_text is required")
        return self


class CondenseResponse(CamelModel):
    condensed: CondensedTicket
    model: str
    prompt_version: str


__all__ = ["CondenseOptions", "CondenseRequest", "CondenseResponse", "CondensedTicket"]
