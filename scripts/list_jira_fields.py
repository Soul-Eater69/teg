"""List Jira fields (id + display name) grouped by concept, to find custom-field ids.

Hits /rest/api/2/field (the whole field catalogue - no specific issue needed) and groups
matches under each search term, so the Business Need / Description / L2 / L3 custom-field
ids are easy to read off. Pass --grep to override the default terms.

Usage (needs Jira creds in .env):
  uv run python scripts/list_jira_fields.py
  uv run python scripts/list_jira_fields.py --grep "business need" "level 3" capability
"""

from __future__ import annotations

import argparse
import asyncio

import httpx

from teg.config.settings import load_settings

_DEFAULT_TERMS = [
    "business need", "description", "capability",
    "level 2", "level 3", "l2", "l3", "stage", "value stream",
]


async def main(args: argparse.Namespace) -> None:
    settings = load_settings()
    http = httpx.AsyncClient(
        base_url=settings.jira_base_url,
        headers={"Authorization": f"Bearer {settings.jira_token}"},
        timeout=settings.jira_timeout_seconds,
        verify=settings.jira_verify_ssl,
    )
    try:
        resp = await http.get(f"/rest/api/{settings.jira_api_version}/field")
        resp.raise_for_status()
        fields = resp.json() or []
    finally:
        await http.aclose()

    rows = [(str(f.get("id") or ""), str(f.get("name") or ""), bool(f.get("custom")))
            for f in fields]
    print(f"{len(rows)} fields total\n")

    for term in args.grep:
        wanted = term.lower()
        matches = [r for r in rows if wanted in r[1].lower()]
        print(f"=== '{term}' -> {len(matches)} match(es) ===")
        for field_id, name, custom in sorted(matches, key=lambda r: r[1].lower()):
            tag = "custom" if custom else "system"
            print(f"  {field_id:<22}  {name}  [{tag}]")
        if not matches:
            print("  (none)")
        print()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="List Jira fields grouped by concept.")
    p.add_argument("--grep", nargs="+", default=_DEFAULT_TERMS,
                   help="terms to match against field display names")
    asyncio.run(main(p.parse_args()))
