"""Batch-ingest IDMT tickets from a file into Cosmos docs + the unified search index.

Reads a ticket-ids file (one IDMT id per line; blank lines and '#' comments ignored),
runs ingestion per ticket (embedding the historical doc), writes the Cosmos docs to disk
for you to ingest into Cosmos, and upserts the historical index docs into idp_teg_data.
This is the nightly-batch entrypoint.

Usage:
  uv run python scripts/ingest_tickets.py data/tickets_eda.txt
  uv run python scripts/ingest_tickets.py data/tickets_eda.txt --fresh   # rebuild from scratch
  uv run python scripts/ingest_tickets.py data/tickets_eda.txt --no-upload   # JSON only, no search write

By default this RESUMES from out/idmt and prunes any stale tickets not in the given list.
--fresh ignores prior output entirely and rebuilds from the ticket list.
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


def _project(key: str) -> str:
    return key.split("-", 1)[0].upper() if "-" in key else key.upper()


async def _ingest_one(ingestion, ticket_id: str, sem: asyncio.Semaphore, failed: dict, moved: dict):
    async with sem:
        try:
            result = await ingestion.ingest(ticket_id)
            fetched_key = result.idmt_document.get("key") or ""
            # Jira redirects a MOVED issue: fetching the old key returns the new key. A ticket that
            # was valid (IDMT) at audit time but later moved to another project is no longer in the
            # cohort - skip it (e.g. IDMT-#### -> CBCCA-####).
            if fetched_key and _project(fetched_key) != _project(ticket_id):
                moved[ticket_id] = fetched_key
                print(f"{ticket_id}: SKIPPED - moved to {fetched_key} (different project)")
                return None
            gt = result.idmt_document["properties"]["themes"]
            print(f"{ticket_id}: {len(result.theme_documents)} themes, {len(gt)} VS GT")
            return result
        except Exception as exc:  # one bad ticket must not abort the batch - record it
            failed[ticket_id] = f"{type(exc).__name__}: {exc}"
            print(f"{ticket_id}: ERROR {failed[ticket_id]}")
            return None


def _ticket_id(doc: dict) -> str:
    return doc.get("key") or doc.get("ticketId") or doc.get("sourceId") or ""


def _load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


async def main(tickets_path: str, catalogue_path: str, out_dir: str, upload: bool,
               concurrency: int, fresh: bool) -> None:
    ticket_ids = _read_ticket_ids(tickets_path)
    if not ticket_ids:
        raise SystemExit(f"no ticket ids found in {tickets_path}")
    wanted = set(ticket_ids)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # --fresh: ignore any prior output and rebuild from this ticket list only. Otherwise resume,
    # but PRUNE docs that aren't in the current list (so stale tickets from earlier runs / a
    # different list don't linger - the cumulative-resume trap).
    if fresh:
        idmt_docs, theme_docs, historical_docs = [], [], []
        print(f"--fresh: ignoring prior output, ingesting all {len(ticket_ids)} from {tickets_path}")
    else:
        idmt_docs = [d for d in _load_json(out / "cosmos_idmt.json") if _ticket_id(d) in wanted]
        keep_ids = {_ticket_id(d) for d in idmt_docs}
        theme_docs = [d for d in _load_json(out / "cosmos_themes.json") if d.get("parentRef") in
                      {d2.get("sourceId") for d2 in idmt_docs}]
        historical_docs = [d for d in _load_json(out / "index_historical.json")
                           if (d.get("key") or d.get("sourceId")) in wanted]
        pruned = len(_load_json(out / "cosmos_idmt.json")) - len(idmt_docs)
        if pruned:
            print(f"pruned {pruned} stale doc(s) not in {tickets_path}")
    done = {_ticket_id(d) for d in idmt_docs}
    todo = [t for t in ticket_ids if t not in done]
    if done:
        print(f"resuming: {len(done)} tickets already ingested, {len(todo)} to go")
    print(f"ingesting {len(todo)} tickets (concurrency={concurrency})")

    settings = load_settings()
    failed: dict[str, str] = {}
    moved: dict[str, str] = {}
    if todo:
        ingestion = build_idmt_ingestion(settings, catalogue_path=catalogue_path, embed=True)
        sem = asyncio.Semaphore(concurrency)
        results = await asyncio.gather(*(_ingest_one(ingestion, t, sem, failed, moved) for t in todo))
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
    if moved:
        (out / "moved_tickets.json").write_text(json.dumps(moved, indent=2), encoding="utf-8")
    print(f"ok={len(idmt_docs)} fail={len(failed)} moved={len(moved)}; wrote cosmos_idmt.json + "
          f"cosmos_themes.json + index_historical.json to {out}/"
          + (f"  ({len(failed)} failures -> failed_tickets.txt; re-run to retry)" if failed else "")
          + (f"  ({len(moved)} moved out of project -> moved_tickets.json, skipped)" if moved else ""))

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
    parser.add_argument("--fresh", action="store_true",
                        help="ignore prior output and rebuild from this ticket list only "
                             "(drops stale tickets from earlier runs / a different list)")
    args = parser.parse_args()
    asyncio.run(
        main(args.tickets_file, args.catalogue, args.out, args.upload, args.concurrency, args.fresh)
    )
