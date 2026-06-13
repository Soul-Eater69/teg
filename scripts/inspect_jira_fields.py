"""Dump an issue's populated fields (id, display name, value) to find custom-field ids.

Use it on a known-good Epic to see which customfield holds the L2 / L3 capabilities, and on
a Theme to confirm the Business Needs field - then pass them to build_stage_ground_truth.py.

Usage (needs Jira creds in .env):
  uv run python scripts/inspect_jira_fields.py EPIC-1234
  uv run python scripts/inspect_jira_fields.py GROUP-9 --all          # include empty fields
  uv run python scripts/inspect_jira_fields.py EPIC-1234 --grep capab # filter by name/value
"""

from __future__ import annotations

import argparse
import asyncio

import httpx

from teg.config.settings import load_settings


def _short(value: object, limit: int = 160) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit] + " ..."


async def main(args: argparse.Namespace) -> None:
    settings = load_settings()
    http = httpx.AsyncClient(
        base_url=settings.jira_base_url,
        headers={"Authorization": f"Bearer {settings.jira_token}"},
        timeout=settings.jira_timeout_seconds,
        verify=settings.jira_verify_ssl,
    )
    try:
        resp = await http.get(
            f"/rest/api/{settings.jira_api_version}/issue/{args.issue}",
            params={"expand": "names"},
        )
        resp.raise_for_status()
        payload = resp.json() or {}
    finally:
        await http.aclose()

    names = payload.get("names") or {}  # field id -> display name
    fields = payload.get("fields") or {}
    grep = (args.grep or "").lower()

    print(f"{args.issue}: {_short((fields.get('issuetype') or {}).get('name'))} | "
          f"{_short(fields.get('summary'))}\n")
    rows = []
    for field_id, value in fields.items():
        if value in (None, "", [], {}) and not args.all:
            continue
        display = str(names.get(field_id) or "")
        if grep and grep not in display.lower() and grep not in str(value).lower():
            continue
        rows.append((field_id, display, _short(value)))

    width = max((len(r[0]) for r in rows), default=12)
    for field_id, display, value in sorted(rows, key=lambda r: r[1].lower()):
        print(f"  {field_id:<{width}}  {display:<32}  {value}")
    print(f"\n{len(rows)} fields shown")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Dump an issue's fields to find custom-field ids.")
    p.add_argument("issue", help="issue key (an Epic, Theme/GROUP, or IDMT)")
    p.add_argument("--all", action="store_true", help="include empty fields")
    p.add_argument("--grep", default="", help="filter by field name or value substring")
    asyncio.run(main(p.parse_args()))
