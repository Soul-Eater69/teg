"""Print the LIVE deployed index schema's per-field attributes (what Azure actually has).

The local data/idp_teg_data_index.json is the intended definition; this shows what is actually
deployed, so a drift (e.g. every field searchable -> BM25 clause blowup) is visible.

Usage:
  uv run python scripts/show_index.py
"""

from __future__ import annotations

import asyncio

import httpx

from teg.config.settings import load_settings
from teg.integrations.search.credential import search_bearer_token


def _attrs(f: dict) -> str:
    on = [a for a in ("searchable", "filterable", "sortable", "facetable", "retrievable") if f.get(a)]
    return ", ".join(on) or "-"


async def main() -> None:
    settings = load_settings()
    base = settings.search_endpoint.rstrip("/")
    name = settings.search_index
    params = {"api-version": settings.search_api_version}
    token = search_bearer_token(settings)
    headers = ({"Authorization": f"Bearer {token}"} if token
               else {"api-key": settings.search_api_key})

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{base}/indexes/{name}", params=params, headers=headers)
        r.raise_for_status()
        idx = r.json()
        # total doc count + per-entityType count (so an empty index is obvious)
        cnt = await client.get(f"{base}/indexes/{name}/docs/$count", params=params, headers=headers)
        total = cnt.text.strip() if cnt.status_code == 200 else "?"
        facet = await client.post(
            f"{base}/indexes/{name}/docs/search", params=params, headers=headers,
            json={"search": "*", "top": 0, "facets": ["entityType"]},
        )
        by_type = {}
        if facet.status_code == 200:
            for f in (facet.json().get("@search.facets", {}) or {}).get("entityType", []):
                by_type[f.get("value")] = f.get("count")

    searchable: list[str] = []

    def walk(fields, prefix=""):
        for f in fields:
            print(f"{prefix}{f['name']:28} [{f['type']}]  -> {_attrs(f)}")
            if f.get("searchable") and not f["type"].startswith("Collection(Edm.Single"):
                searchable.append(prefix + f["name"])
            if f.get("fields"):
                walk(f["fields"], prefix + "  ")

    print(f"LIVE index '{name}':  {total} documents")
    print(f"  by entityType: {by_type or '(none - index is EMPTY)'}\n")
    walk(idx.get("fields", []))
    print(f"\nSearchable TEXT fields (BM25 clause multiplier): {searchable or ['(none)']}")
    print(f"-> clause limit hit when query_terms x {len(searchable)} > 3000")


if __name__ == "__main__":
    asyncio.run(main())
