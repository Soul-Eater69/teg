"""Create (or update) the unified Azure Search index from its JSON definition.

data/idp_teg_data_index.json is the single source of truth for the schema (fields,
HNSW vector profile, semantic config). This PUTs it to the search service using the
Settings creds - PUT is create-or-update, so it's idempotent.

Note: Azure rejects breaking changes (e.g. vector dimensions) on an existing index;
use --recreate to delete then create when the schema changed incompatibly. --recreate
DROPS the index and all its documents.

Usage:
  uv run python scripts/create_index.py
  uv run python scripts/create_index.py --definition data/idp_teg_data_index.json --recreate
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from teg.config.settings import load_settings


async def main(definition_path: str, recreate: bool) -> None:
    settings = load_settings()
    if not settings.search_endpoint or not settings.search_api_key:
        raise SystemExit("TEG_SEARCH_ENDPOINT and TEG_SEARCH_API_KEY are required")

    definition = json.loads(Path(definition_path).read_text(encoding="utf-8"))
    index_name = definition["name"]
    base = settings.search_endpoint.rstrip("/")
    params = {"api-version": settings.search_api_version}
    headers = {"api-key": settings.search_api_key, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        if recreate:
            drop = await client.delete(f"{base}/indexes/{index_name}", params=params, headers=headers)
            if drop.status_code not in (204, 404):
                raise SystemExit(f"delete index failed [{drop.status_code}]: {drop.text}")
            print(f"dropped index '{index_name}' ({drop.status_code})")

        response = await client.put(
            f"{base}/indexes/{index_name}",
            params=params,
            headers=headers,
            content=json.dumps(definition),
        )

    if response.status_code not in (200, 201):
        raise SystemExit(f"create index failed [{response.status_code}]: {response.text}")
    fields = len(definition.get("fields", []))
    print(f"index '{index_name}' ready ({response.status_code}): {fields} top-level fields -> {base}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--definition", default="data/idp_teg_data_index.json")
    parser.add_argument("--recreate", action="store_true", help="DROP then create (loses all docs)")
    args = parser.parse_args()
    asyncio.run(main(args.definition, args.recreate))
