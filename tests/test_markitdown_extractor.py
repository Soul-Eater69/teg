"""MarkitdownExtractor tests with a fake converter - no real markitdown needed."""

from __future__ import annotations

from teg.integrations.files.markitdown_extractor import MarkitdownExtractor, _clean

ZWSP = chr(0x200B)  # zero-width space


class _FakeResult:
    def __init__(self, text: str) -> None:
        self.text_content = text


class _FakeMd:
    def __init__(self, text: str) -> None:
        self._text = text
        self.seen_name: str | None = None

    def convert_stream(self, stream) -> _FakeResult:
        self.seen_name = stream.name
        return _FakeResult(self._text)


def test_extract_passes_filename_and_cleans_output() -> None:
    md = _FakeMd(f"# Deck\n\n\n\nbody{ZWSP}text  \n")
    extractor = MarkitdownExtractor(md=md)

    out = extractor.extract("idea_card.pptx", b"raw-bytes")

    assert md.seen_name == "idea_card.pptx"  # markitdown infers format from the name
    assert ZWSP not in out
    assert "\n\n\n" not in out
    assert out == "# Deck\n\nbodytext"


def test_extract_handles_empty_text() -> None:
    assert MarkitdownExtractor(md=_FakeMd("")).extract("a.pdf", b"x") == ""


def test_clean_normalizes_and_trims() -> None:
    assert _clean("caf\xe9\xa0bar\n\n\n\nend   ") == "caf\xe9 bar\n\nend"
