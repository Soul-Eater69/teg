"""clean_text: normalise extracted attachment/Jira text for storage."""

from __future__ import annotations

from teg.ingestion.documents.text_cleaning import clean_text


def test_normalises_line_endings_and_collapses_blank_lines() -> None:
    raw = "Line one\r\nLine two\r\n\r\n\r\n\r\nLine three"
    assert clean_text(raw) == "Line one\nLine two\n\nLine three"


def test_strips_control_chars_nbsp_and_zero_width() -> None:
    raw = "Pay\x07ment due​ now\x00"
    assert clean_text(raw) == "Payment due now"


def test_collapses_space_and_tab_runs_and_trims_lines() -> None:
    raw = "   prior    \t auth   \n\t  claims  "
    assert clean_text(raw) == "prior auth\nclaims"


def test_empty_and_whitespace_only() -> None:
    assert clean_text("") == ""
    assert clean_text("   \n\r\n\t  ") == ""


def test_keeps_paragraph_structure() -> None:
    raw = "[DESCRIPTION]\nMember enrollment change.\n\n[DOCUMENT: idea.pdf]\nDetails here."
    assert clean_text(raw) == "[DESCRIPTION]\nMember enrollment change.\n\n[DOCUMENT: idea.pdf]\nDetails here."
