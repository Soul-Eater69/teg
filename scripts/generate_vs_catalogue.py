"""Generate the catalogue documents from the Sightline maps.

Cosmos docs are written as JSON for you to ingest. The VS index docs are written too;
with --embed they include content_vector via the IDP embeddings client.

Usage:
  uv run python scripts/generate_vs_catalogue.py data/value_stream_capability_map.json
  uv run python scripts/generate_vs_catalogue.py data/value_stream_capability_map.json --embed
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from teg.config.settings import load_settings
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.ingestion.documents.value_stream_documents import (
    build_catalogue_content,
    build_catalogue_document,
    build_index_document,
)
from teg.integrations.embeddings import build_embeddings_client
from teg.ingestion.upload.search_uploader import build_search_uploader


async def main(map_path: str, out_dir: str, embed: bool, upload: bool) -> None:
    catalogue = load_value_stream_catalogue(map_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    cosmos_docs = [build_catalogue_document(vs) for vs in catalogue]
    _write(out / "cosmos_value_streams.json", cosmos_docs)

    vectors: list[list[float] | None] = [None] * len(catalogue)
    if embed:
        client = build_embeddings_client(load_settings())
        vectors = list(await client.embed_many([build_catalogue_content(vs) for vs in catalogue]))
    index_docs = [build_index_document(vs, vec) for vs, vec in zip(catalogue, vectors)]
    _write(out / "index_value_streams.json", index_docs)

    stages = sum(len(vs.stages) for vs in catalogue)
    caps = sum(len(s.capabilities) for vs in catalogue for s in vs.stages)
    print(
        f"{len(catalogue)} value streams ({stages} stages, {caps} capability links) -> {out}/"
        f"{' (embedded)' if embed else ' (no vectors; pass --embed)'}"
    )

    if upload:
        if not embed:
            raise SystemExit("--upload requires --embed (the index needs content_vector)")
        settings = load_settings()
        uploader = build_search_uploader(settings)
        try:
            report = await uploader.upload(index_docs)
        finally:
            await uploader.close()
        print(f"upserted {report.succeeded}/{len(index_docs)} value stream docs -> {settings.search_index}")
        for failure in report.failures:
            print(f"  FAILED {failure.document_id}: [{failure.status_code}] {failure.error_message}")


def _write(path: Path, docs: list[dict]) -> None:
    path.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("map_path", nargs="?", default="data/value_stream_capability_map.json")
    parser.add_argument("--out", default="out/catalogue")
    parser.add_argument("--embed", action="store_true")
    parser.add_argument("--upload", action="store_true", help="upsert into idp_teg_data (needs --embed)")
    args = parser.parse_args()
    asyncio.run(main(args.map_path, args.out, args.embed, args.upload))
