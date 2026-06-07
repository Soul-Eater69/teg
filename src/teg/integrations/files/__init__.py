"""File text extraction: protocol + markitdown implementation."""

from teg.integrations.files.extractor import AttachmentTextExtractor
from teg.integrations.files.markitdown_extractor import (
    MarkitdownExtractor,
    build_attachment_extractor,
)

__all__ = ["AttachmentTextExtractor", "MarkitdownExtractor", "build_attachment_extractor"]
