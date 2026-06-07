"""markitdown-backed attachment text extraction (PPT/PPTX/PDF/DOC/DOCX).

Converts attachment bytes to text via markitdown and applies a light cleanup.
OCR fallback for image-heavy decks (tesseract/PyMuPDF) is intentionally out of
scope here - it needs system deps and is a separate ticket.
"""

from __future__ import annotations

import io
import re
import unicodedata

try:  # markitdown is an optional runtime extra; tests inject a fake converter.
    from markitdown import MarkItDown
except Exception:  # pragma: no cover - import guarded so the module always loads
    MarkItDown = None  # type: ignore[assignment]

# Zero-width chars: ZWSP, ZWNJ, ZWJ, BOM. Built via chr() to keep source ASCII-only.
_ZERO_WIDTH = re.compile("[" + "".join(map(chr, (0x200B, 0x200C, 0x200D, 0xFEFF))) + "]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_EXTRA_BLANK_LINES = re.compile(r"\n{3,}")


class MarkitdownExtractor:
    """AttachmentTextExtractor backed by markitdown."""

    def __init__(self, md: object | None = None) -> None:
        if md is None:
            if MarkItDown is None:
                raise ImportError("markitdown is required: install with the 'extract' extra")
            md = MarkItDown()
        self._md = md

    def extract(self, filename: str, content: bytes) -> str:
        stream = io.BytesIO(content)
        stream.name = filename  # markitdown infers the format from the name
        text = self._md.convert_stream(stream).text_content or ""
        return _clean(text)


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = _ZERO_WIDTH.sub("", text)
    text = _CONTROL.sub(" ", text)
    text = text.replace("\xa0", " ")
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return _EXTRA_BLANK_LINES.sub("\n\n", text).strip()


def build_attachment_extractor() -> MarkitdownExtractor:
    return MarkitdownExtractor()
