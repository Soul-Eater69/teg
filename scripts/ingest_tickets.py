"""Batch-ingest IDMT tickets from a file into Cosmos docs + the unified search index.

Reads a ticket-ids file (one IDMT id per line; blank lines and '#' comments ignored),
runs ingestion per ticket (embedding the historical doc), writes the Cosmos docs to disk
for you to ingest into Cosmos, and upserts the historical index docs into idp_teg_data.
This is the nightly-batch entrypoint.

Usage:
  uv run python scripts/ingest_tickets.py tickets.txt \
      --catalogue data/value_stream_capability_map.json
  uv run python scripts/ingest_tickets.py tickets.txt --no-upload   # JSON only, no search write
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from teg.bootstrap import build_idmt_ingestion
from teg.config.settings import load_settings
from teg.ingestion.upload.search_uploader import build_search_uploader


def _read_ticket_ids(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


async def _ingest_one(ingestion, ticket_id: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            result = await ingestion.ingest(ticket_id)
            gt = result.idmt_document["properties"]["themes"]
            print(f"{ticket_id}: {len(result.theme_documents)} themes, {len(gt)} VS GT")
            return result
        except Exception as exc:  # one bad ticket must not abort the batch
            print(f"{ticket_id}: ERROR {type(exc).__name__}: {exc}")
            return None


async def main(tickets_path: str, catalogue_path: str, out_dir: str, upload: bool, concurrency: int) -> None:
    ticket_ids = _read_ticket_ids(tickets_path)
    if not ticket_ids:
        raise SystemExit(f"no ticket ids found in {tickets_path}")
    print(f"ingesting {len(ticket_ids)} tickets (concurrency={concurrency})")

    settings = load_settings()
    ingestion = build_idmt_ingestion(settings, catalogue_path=catalogue_path, embed=True)
    sem = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*(_ingest_one(ingestion, t, sem) for t in ticket_ids))

    idmt_docs: list[dict] = []
    theme_docs: list[dict] = []
    historical_docs: list[dict] = []
    for result in results:
        if result is None:
            continue
        idmt_docs.append(result.idmt_document)
        theme_docs.extend(result.theme_documents)
        historical_docs.append(result.historical_index_document)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "cosmos_idmt.json", idmt_docs)
    _write(out / "cosmos_themes.json", theme_docs)
    _write(out / "index_historical.json", historical_docs)
    print(
        f"ok={len(idmt_docs)} fail={len(ticket_ids) - len(idmt_docs)}; "
        f"wrote cosmos_idmt.json + cosmos_themes.json + index_historical.json to {out}/"
    )

    if not upload:
        print("--no-upload: skipped search upload")
        return
    uploader = build_search_uploader(settings)
    try:
        count = await uploader.upload(historical_docs)
    finally:
        await uploader.close()
    print(f"upserted {count} historical docs -> {settings.search_index}")


def _write(path: Path, docs: list[dict]) -> None:
    path.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tickets_file", help="text file with one IDMT id per line")
    parser.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    parser.add_argument("--out", default="out/idmt")
    parser.add_argument("--no-upload", dest="upload", action="store_false")
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(
        main(args.tickets_file, args.catalogue, args.out, args.upload, args.concurrency)
    )
