"""Resolve a Theme's Value Stream from its Jira GROUP summary.

The GROUP summary encodes the VS name (e.g. "CP 2027 Guided Health Plans : Appeal
Decision" -> "Appeal Decision"). We clean it, then resolve against the approved
catalogue in three tiers: normalized-exact -> difflib fuzzy -> LLM verifier. Anything
that still resolves to no approved VS is dropped (GT must be an approved value stream).
"""

from __future__ import annotations

import difflib
import re

from pydantic import Field

from teg.domain.base import CamelModel
from teg.integrations.llm import LLMClient
from teg.ingestion.catalogues.models import CatalogueValueStream
from teg.prompts.loader import load_prompt

_FUZZY_THRESHOLD = 0.86

_PREFIX_RE = re.compile(
    r"^(?:(?:GROUP-\d+(?:,\s*|\s*(?:&|and)\s*|\s+)*)+|THEME\s*#?\s*\d+)(?:\s*\([^)]+\))?\s*:\s*",
    re.IGNORECASE,
)
_PRODUCT_PREFIX_RE = re.compile(r"^[A-Z]{2,5}\s+\d+(?:\.\d+)*\s+(?=\S)")
_SEPARATOR_RE = re.compile(r"\s[-–—]\s+|:\s+")


def clean_value_stream_name(summary: str) -> str:
    """Strip the GROUP/product/ER prefix and take the value-stream tail of the summary."""
    text = (summary or "").strip()
    if not text:
        return ""
    text = _PREFIX_RE.sub("", text)
    text = _PRODUCT_PREFIX_RE.sub("", text)
    matches = list(_SEPARATOR_RE.finditer(text))
    if matches:
        tail = text[matches[-1].end() :].strip()
        if len(tail) >= 4:
            text = tail
    return re.sub(r"\s{2,}", " ", text).strip(" -:")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


class VsVerificationItem(CamelModel):
    raw_name: str
    approved_value_stream: str | None = None


class VsVerification(CamelModel):
    mappings: list[VsVerificationItem] = Field(default_factory=list)


class ValueStreamResolver:
    def __init__(self, catalogue: list[CatalogueValueStream]) -> None:
        self._by_norm: dict[str, tuple[str, str]] = {}
        self._names: list[str] = []
        for vs in catalogue:
            self._by_norm[_norm(vs.value_stream_name)] = (vs.value_stream_id, vs.value_stream_name)
            self._names.append(vs.value_stream_name)

    async def resolve(
        self, theme_summaries: list[str], llm_client: LLMClient
    ) -> dict[str, tuple[str, str] | None]:
        """Map each theme summary to (valueStreamId, valueStreamName) or None (dropped)."""
        raws = {summary: clean_value_stream_name(summary) for summary in theme_summaries}
        result: dict[str, tuple[str, str] | None] = {}
        unresolved: set[str] = set()
        for summary, raw in raws.items():
            hit = self._lookup(raw)
            result[summary] = hit
            if hit is None and raw:
                unresolved.add(raw)

        if unresolved:
            mapping = await self._verify(sorted(unresolved), llm_client)
            for summary, raw in raws.items():
                if result[summary] is None and mapping.get(raw):
                    result[summary] = self._lookup(mapping[raw])
        return result

    def _lookup(self, name: str) -> tuple[str, str] | None:
        if not name:
            return None
        return self._by_norm.get(_norm(name)) or self._fuzzy(name)

    def _fuzzy(self, name: str) -> tuple[str, str] | None:
        norm = _norm(name)
        best: tuple[str, str] | None = None
        best_score = 0.0
        for catalogue_norm, hit in self._by_norm.items():
            score = difflib.SequenceMatcher(None, norm, catalogue_norm).ratio()
            if score > best_score:
                best_score, best = score, hit
        return best if best_score >= _FUZZY_THRESHOLD else None

    async def _verify(self, raw_names: list[str], llm_client: LLMClient) -> dict[str, str | None]:
        prompt = load_prompt("ingestion/value_stream_verifier")
        system, user = prompt.render(
            approved_value_streams="\n".join(f"- {name}" for name in self._names),
            unresolved="\n".join(f"- {name}" for name in raw_names),
        )
        result = await llm_client.complete(system=system, user=user, schema=VsVerification)
        return {item.raw_name: (item.approved_value_stream or None) for item in result.mappings}
