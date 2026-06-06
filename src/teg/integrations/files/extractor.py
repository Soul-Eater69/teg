"""Attachment text extraction protocol.

Extracts plain text from an attachment's bytes (PPT/PPTX/PDF/DOC/DOCX). The
markitdown implementation lands in TEG-32; condense depends only on this protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AttachmentTextExtractor(Protocol):
    def extract(self, filename: str, content: bytes) -> str: ...
