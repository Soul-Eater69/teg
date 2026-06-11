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


async def _ingest_one(ingestion, ticket_id: str, sem: asyncio.Semaphore, failed: dict):
    async with sem:
        try:
            result = await ingestion.ingest(ticket_id)
            gt = result.idmt_document["properties"]["themes"]
            print(f"{ticket_id}: {len(result.theme_documents)} themes, {len(gt)} VS GT")
            return result
        except Exception as exc:  # one bad ticket must not abort the batch - record it
            failed[ticket_id] = f"{type(exc).__name__}: {exc}"
            print(f"{ticket_id}: ERROR {failed[ticket_id]}")
            return None


def _ticket_id(doc: dict) -> str:
    return doc.get("ticketId") or doc.get("sourceId") or doc.get("id") or ""


def _load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


async def main(tickets_path: str, catalogue_path: str, out_dir: str, upload: bool, concurrency: int) -> None:
    ticket_ids = _read_ticket_ids(tickets_path)
    if not ticket_ids:
        raise SystemExit(f"no ticket ids found in {tickets_path}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Resume: keep already-ingested tickets from a prior run, only fetch the missing ones.
    idmt_docs = _load_json(out / "cosmos_idmt.json")
    theme_docs = _load_json(out / "cosmos_themes.json")
    historical_docs = _load_json(out / "index_historical.json")
    done = {_ticket_id(d) for d in idmt_docs}
    todo = [t for t in ticket_ids if t not in done]
    if done:
        print(f"resuming: {len(done)} tickets already ingested, {len(todo)} to go")
    print(f"ingesting {len(todo)} tickets (concurrency={concurrency})")

    settings = load_settings()
    failed: dict[str, str] = {}
    if todo:
        ingestion = build_idmt_ingestion(settings, catalogue_path=catalogue_path, embed=True)
        sem = asyncio.Semaphore(concurrency)
        results = await asyncio.gather(*(_ingest_one(ingestion, t, sem, failed) for t in todo))
        for result in results:
            if result is None:
                continue
            idmt_docs.append(result.idmt_document)
            theme_docs.extend(result.theme_documents)
            historical_docs.append(result.historical_index_document)

    # Persist BEFORE upload so the fetch+condense work is never lost to an upload failure.
    _write(out / "cosmos_idmt.json", idmt_docs)
    _write(out / "cosmos_themes.json", theme_docs)
    _write(out / "index_historical.json", historical_docs)
    if failed:
        (out / "failed_tickets.txt").write_text("\n".join(failed) + "\n", encoding="utf-8")
        (out / "failed_tickets.json").write_text(json.dumps(failed, indent=2), encoding="utf-8")
    print(f"ok={len(idmt_docs)} fail={len(failed)}; wrote cosmos_idmt.json + cosmos_themes.json + "
          f"index_historical.json to {out}/"
          + (f"  ({len(failed)} failures -> failed_tickets.txt; re-run the same command to retry them)"
             if failed else ""))

    if not upload:
        print("--no-upload: skipped search upload (run scripts/upload_index.py on index_historical.json)")
        return
    try:
        uploader = build_search_uploader(settings)
    except Exception as exc:
        print(f"\n[!] upload skipped: {exc}\n    docs are saved - install the extra and run:"
              f"\n    uv run python scripts/upload_index.py {out}/index_historical.json")
        return
    try:
        report = await uploader.upload(historical_docs)
    finally:
        await uploader.close()
    print(f"upserted {report.succeeded}/{len(historical_docs)} historical docs -> {settings.search_index}")
    for failure in report.failures:
        print(f"  FAILED {failure.document_id}: [{failure.status_code}] {failure.error_message}")


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
