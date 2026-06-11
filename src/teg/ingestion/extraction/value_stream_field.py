"""Parse a Theme's "Business Value Stream" field into (value stream name, id).

The linked Theme carries its Value Stream directly in a Jira field formatted
``<name> {<id>}`` (e.g. ``Configure Price {VS1024}``). We read it as-is - no catalogue
fuzzy match, no LLM verification. Tolerates a plain string, a Jira select object
(``{"value": ...}`` / ``{"name": ...}``), or a list of those (first that parses wins).
"""

from __future__ import annotations

import re

# "<name> {<id>}" - name is everything before the last {...}; id is inside the braces.
_VS_PATTERN = re.compile(r"^\s*(?P<name>.*?)\s*\{\s*(?P<id>[^{}]+?)\s*\}\s*$")


def parse_value_stream(raw: object) -> tuple[str, str] | None:
    """Return (name, id) from a Business Value Stream field value, or None if absent/unparseable."""
    if raw is None:
        return None
    if isinstance(raw, list):
        for item in raw:
            parsed = parse_value_stream(item)
            if parsed:
                return parsed
        return None
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("name") or ""
    match = _VS_PATTERN.match(str(raw))
    if not match:
        return None
    return match.group("name").strip(), match.group("id").strip()
