"""Upsert already-generated index JSON files into the unified search index.

Decouples upload from the expensive generate step: generate the index docs once
(generate_vs_catalogue.py / ingest_tickets.py), inspect them, then upload here - and
re-upload cheaply without re-fetching Jira or re-running the LLM. Each file is a JSON
array of index documents (the index_*.json the generators write).

Usage:
  uv run python scripts/upload_index.py out/catalogue/index_value_streams.json
  uv run python scripts/upload_index.py out/idmt/index_historical.json out/catalogue/index_value_streams.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from teg.config.settings import load_settings
from teg.ingestion.upload.search_uploader import build_search_uploader


async def main(paths: list[str]) -> None:
    documents: list[dict] = []
    for path in paths:
        docs = json.loads(Path(path).read_text(encoding="utf-8"))
        missing_vectors = sum(1 for d in docs if not d.get("content_vector"))
        if missing_vectors:
            raise SystemExit(
                f"{path}: {missing_vectors} docs have no content_vector - "
                "regenerate with --embed before uploading"
            )
        documents.extend(docs)
        print(f"{path}: {len(docs)} docs")

    settings = load_settings()
    uploader = build_search_uploader(settings)
    try:
        report = await uploader.upload(documents)
    finally:
        await uploader.close()

    print(f"upserted {report.succeeded}/{len(documents)} docs -> {settings.search_index}")
    for failure in report.failures:
        print(f"  FAILED {failure.document_id}: [{failure.status_code}] {failure.error_message}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="index_*.json files to upload")
    args = parser.parse_args()
    asyncio.run(main(args.paths))
