"""Ingest the local Cosmos docs (out/idmt/cosmos_*.json) into Cosmos.

Reads the docs already built on disk, restamps their lifecycle timestamps to NOW (the ingestion-run
time, not the extraction time), and upserts them into the one container via the Cosmos writer.
Idempotent - re-running overwrites by the deterministic id, never duplicates.

    uv sync --extra cosmos
    uv run python scripts/cosmos_ingest.py --limit 2     # smoke test: write 2 docs, confirm in portal
    uv run python scripts/cosmos_ingest.py               # full ingest

Needs the Cosmos env (AZURE_COSMOS_DB_URL / _DB_NAME / _CONTAINER_NAME + the AZURE_*_DEV service
principal, which must have the "Cosmos DB Built-in Data Contributor" data role).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from teg.bootstrap import load_settings
from teg.ingestion.documents.idmt_documents import _now, restamp
from teg.integrations.cosmos import build_cosmos_writer, to_cosmos_doc

_FILES = ("cosmos_idmt.json", "cosmos_themes.json")


def _load(out: Path, limit: int | None) -> list[dict]:
    docs: list[dict] = []
    for name in _FILES:
        path = out / name
        if not path.exists():
            print(f"skip {path} (not found)")
            continue
        loaded = json.loads(path.read_text(encoding="utf-8"))
        print(f"{name}: {len(loaded)} docs")
        docs.extend(loaded)
    return docs[:limit] if limit else docs


async def main(out_dir: str, limit: int | None) -> None:
    docs = _load(Path(out_dir), limit)
    if not docs:
        print("nothing to ingest")
        return

    when = _now()  # one timestamp for the whole run
    for doc in docs:
        restamp(doc, when)
    # Adapt to the org Cosmos schema (domain=WORKITEM, uppercase discriminators, drop themes).
    docs = [to_cosmos_doc(doc) for doc in docs]

    writer = build_cosmos_writer(load_settings())
    try:
        written = await writer.upsert(docs)
    finally:
        await writer.close()
    print(f"upserted {written} docs into Cosmos (lifecycle stamped {when})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="out/idmt", help="directory holding the cosmos_*.json files")
    parser.add_argument("--limit", type=int, default=0, help="upsert only the first N docs (smoke test)")
    args = parser.parse_args()
    asyncio.run(main(args.dir, args.limit or None))
