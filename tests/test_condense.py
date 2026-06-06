"""Condense unit tests. All clients are fakes - no live Jira/LLM calls."""

from __future__ import annotations

import json

import pytest

from teg.condense.attachment_ranker import select_attachments
from teg.condense.condenser import condense
from teg.condense.ticket_context import resolve_from_ticket
from teg.contracts.condense_io import CondenseRequest
from teg.integrations.jira_client import JiraAttachment, JiraTicket
from teg.services.condense_service import CondenseService


# ---- fakes ---------------------------------------------------------------

class FakeJira:
    def __init__(self, ticket: JiraTicket) -> None:
        self._ticket = ticket

    async def fetch_ticket(self, ticket_id: str) -> JiraTicket:
        return self._ticket

    async def download_attachment(self, ticket_id: str, filename: str) -> bytes:
        return f"bytes::{filename}".encode()


class FakeExtractor:
    def extract(self, filename: str, content: bytes) -> str:
        return f"extracted text of {filename}"


_LLM_JSON = {
    "summaryFields": {
        "generatedSummary": "A proposed change to claims intake.",
        "businessProblem": "Manual intake is slow.",
        "businessCapability": "Automated claims intake.",
        "keyTerms": ["claims", "intake"],
        "stakeholders": ["Claims Ops"],
        "systemsAndProducts": ["ClaimsHub"],
    },
    "generationSignals": {
        "marketSegments": [
            {"text": "Medicare members", "source": "DESCRIPTION", "sourceSection": ""}
        ],
        "dependencies": [],
        # other 16 keys intentionally absent -> must become empty lists
    },
}


class FakeLLM:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload if payload is not None else _LLM_JSON

    async def complete(self, *, system: str, user: str, max_output_tokens=None) -> str:
        return "```json\n" + json.dumps(self._payload) + "\n```"


def _ticket(attachments: list[JiraAttachment]) -> JiraTicket:
    return JiraTicket(
        ticket_id="IDMT-1",
        title="Claims Intake Modernization",
        description="Automate manual claims intake.",
        attachments=attachments,
    )


# ---- attachment ranker ---------------------------------------------------

def test_idea_card_is_sole_source_when_present() -> None:
    selection = select_attachments(
        [JiraAttachment("deck.pdf"), JiraAttachment("idea_card.pptx"), JiraAttachment("notes.docx")]
    )
    assert selection.idea_card is not None
    assert selection.idea_card.filename == "idea_card.pptx"
    assert selection.fallback == []


def test_fallback_takes_top_four_ppt_pdf_doc() -> None:
    selection = select_attachments(
        [
            JiraAttachment("a.docx"),
            JiraAttachment("b.pdf"),
            JiraAttachment("c.pptx"),
            JiraAttachment("d.pptx"),
            JiraAttachment("e.pdf"),
            JiraAttachment("ignore.txt"),
        ]
    )
    assert selection.idea_card is None
    assert [a.filename for a in selection.fallback] == ["c.pptx", "d.pptx", "b.pdf", "e.pdf"]


# ---- ticket context ------------------------------------------------------

async def test_resolve_prefers_idea_card() -> None:
    ticket = _ticket([JiraAttachment("brief.pdf"), JiraAttachment("idea_card.pptx")])
    ctx = await resolve_from_ticket(ticket, FakeJira(ticket), FakeExtractor())
    assert ctx.primary_source == "idea_card"
    assert ctx.attachments_used == ["idea_card.pptx"]
    assert "[DESCRIPTION]" in ctx.consolidated_text
    assert "[DOCUMENT: idea_card.pptx]" in ctx.consolidated_text


async def test_resolve_falls_back_to_top_attachments() -> None:
    ticket = _ticket([JiraAttachment("a.docx"), JiraAttachment("b.pdf")])
    ctx = await resolve_from_ticket(ticket, FakeJira(ticket), FakeExtractor())
    assert ctx.primary_source == "description_fallback"
    assert ctx.attachments_used == ["b.pdf", "a.docx"]


# ---- condenser -----------------------------------------------------------

async def test_condense_maps_fields_and_keeps_absent_signals_empty() -> None:
    ticket = _ticket([JiraAttachment("idea_card.pptx")])
    ctx = await resolve_from_ticket(ticket, FakeJira(ticket), FakeExtractor())
    condensed = await condense(ctx, FakeLLM())

    assert condensed.summary_fields.generated_summary == "A proposed change to claims intake."
    assert condensed.summary_fields.key_terms == ["claims", "intake"]
    assert len(condensed.generation_signals.market_segments) == 1
    assert condensed.generation_signals.market_segments[0].text == "Medicare members"
    # absent categories never invented:
    assert condensed.generation_signals.notes == []
    assert condensed.generation_signals.reporting_signals == []


# ---- service (Contract A) ------------------------------------------------

async def test_service_condenses_from_ticket_id_and_serializes_camel_case() -> None:
    ticket = _ticket([JiraAttachment("idea_card.pptx")])
    service = CondenseService(FakeJira(ticket), FakeLLM(), FakeExtractor(), model_name="test-model")
    response = await service.condense(CondenseRequest(ticket_id="IDMT-1"))

    data = response.model_dump(by_alias=True)
    assert data["condensed"]["ticketId"] == "IDMT-1"
    assert data["condensed"]["primarySource"] == "idea_card"
    assert data["condensed"]["summaryFields"]["businessProblem"] == "Manual intake is slow."
    assert data["condensed"]["generationSignals"]["marketSegments"][0]["text"] == "Medicare members"
    assert data["model"] == "test-model"


async def test_service_uses_idea_card_text_override() -> None:
    service = CondenseService(FakeJira(_ticket([])), FakeLLM(), FakeExtractor())
    response = await service.condense(
        CondenseRequest(ticket_id="IDMT-9", idea_card_text="Direct idea card text")
    )
    assert response.condensed.primary_source == "idea_card"
    assert response.condensed.raw_text.startswith("[DESCRIPTION]")


def test_request_requires_some_input() -> None:
    # validation now lives on the contract, not the service
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CondenseRequest()
