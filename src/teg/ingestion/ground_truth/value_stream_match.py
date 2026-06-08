"""Resolve a Theme's Value Stream from its Jira GROUP summary.

The GROUP summary encodes the VS name (e.g. "CP 2027 Guided Health Plans : Appeal
Decision"). We resolve against the approved catalogue with the stable canonicalizer
ported from the vs repo: token-normalize (drop noise + numbers) -> suffix candidates ->
exact key -> rapidfuzz WRatio (threshold 90, ambiguity margin 2). Anything still
unresolved goes to the LLM verifier; names that match no approved VS are dropped.
"""

from __future__ import annotations

import re

from pydantic import Field
from rapidfuzz import fuzz, process

from teg.domain.base import CamelModel
from teg.ingestion.catalogues.models import CatalogueValueStream
from teg.integrations.llm import LLMClient
from teg.prompts.loader import load_prompt

_FUZZ_MATCH_THRESHOLD = 90.0
_FUZZ_AMBIGUITY_MARGIN = 2.0
_MIN_SUFFIX_TOKENS = 2
_NOISE_TOKENS = {"apr", "and"}

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


def _tokens(value: str) -> tuple[str, ...]:
    cleaned = clean_value_stream_name(value)
    return tuple(
        token
        for token in re.findall(r"[a-z0-9]+", cleaned.lower())
        if token not in _NOISE_TOKENS and not re.fullmatch(r"\d+(?:\.\d+)?", token)
    )


def _lookup_key(value: str) -> str:
    return " ".join(_tokens(value))


def _candidate_keys(value: str) -> list[str]:
    """Progressive suffixes of the token key (handles the '{ER} {VS}' prefix)."""
    key = _lookup_key(value)
    if not key:
        return []
    parts = key.split()
    out: list[str] = []
    seen: set[str] = set()
    for start in range(len(parts)):
        suffix = " ".join(parts[start:])
        if len(suffix.split()) < _MIN_SUFFIX_TOKENS and start != 0:
            continue
        if suffix in seen:
            continue
        seen.add(suffix)
        out.append(suffix)
    return out


class VsVerificationItem(CamelModel):
    raw_name: str
    approved_value_stream: str | None = None


class VsVerification(CamelModel):
    mappings: list[VsVerificationItem] = Field(default_factory=list)


class ValueStreamResolver:
    def __init__(self, catalogue: list[CatalogueValueStream]) -> None:
        self._by_key: dict[str, tuple[str, str]] = {}
        self._keys: list[str] = []
        self._names: list[str] = []
        for vs in catalogue:
            key = _lookup_key(vs.value_stream_name)
            if key:
                self._by_key[key] = (vs.value_stream_id, vs.value_stream_name)
                self._keys.append(key)
            self._names.append(vs.value_stream_name)

    async def resolve(
        self, theme_summaries: list[str], llm_client: LLMClient
    ) -> dict[str, tuple[str, str] | None]:
        """Map each theme summary to (valueStreamId, valueStreamName) or None (dropped)."""
        result: dict[str, tuple[str, str] | None] = {}
        cleaned: dict[str, str] = {}
        unresolved: set[str] = set()
        for summary in theme_summaries:
            hit = self._canonicalize(summary)
            result[summary] = hit
            if hit is None:
                raw = clean_value_stream_name(summary)
                if raw:
                    cleaned[summary] = raw
                    unresolved.add(raw)

        if unresolved:
            mapping = await self._verify(sorted(unresolved), llm_client)
            for summary in theme_summaries:
                if result[summary] is None:
                    approved = mapping.get(cleaned.get(summary, ""))
                    if approved:
                        result[summary] = self._by_key.get(_lookup_key(approved))
        return result

    def _canonicalize(self, summary: str) -> tuple[str, str] | None:
        candidates = _candidate_keys(summary)
        if not candidates:
            return None
        for key in candidates:
            if key in self._by_key:
                return self._by_key[key]

        best: dict[tuple[str, str], float] = {}
        for key in candidates:
            for matched_key, score, _ in process.extract(
                key, self._keys, scorer=fuzz.WRatio, limit=3
            ):
                hit = self._by_key.get(matched_key)
                if hit:
                    best[hit] = max(best.get(hit, 0.0), float(score))
        if not best:
            return None

        ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
        top_hit, top_score = ranked[0]
        if top_score < _FUZZ_MATCH_THRESHOLD:
            return None
        if len(ranked) > 1 and ranked[1][1] >= top_score - _FUZZ_AMBIGUITY_MARGIN:
            return None  # ambiguous - two approved VS too close
        return top_hit

    async def _verify(self, raw_names: list[str], llm_client: LLMClient) -> dict[str, str | None]:
        prompt = load_prompt("ingestion/value_stream_verifier")
        system, user = prompt.render(
            approved_value_streams="\n".join(f"- {name}" for name in self._names),
            unresolved="\n".join(f"- {name}" for name in raw_names),
        )
        result = await llm_client.complete(system=system, user=user, schema=VsVerification)
        return {item.raw_name: (item.approved_value_stream or None) for item in result.mappings}
