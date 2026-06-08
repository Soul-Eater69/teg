"""Generate Cosmos IDMT/ER + Theme docs from live Jira for given IDMT ticket ids.

Needs .env (Jira + IDP/LLM) and the catalogue map (for theme -> VS resolution).

Usage:
  uv run python scripts/generate_idmt_docs.py IDMT-19761 IDMT-20000 \
      --catalogue data/value_stream_capability_map.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from teg.bootstrap import build_idmt_ingestion


async def main(ticket_ids: list[str], catalogue_path: str, out_dir: str) -> None:
    ingestion = build_idmt_ingestion(catalogue_path=catalogue_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    idmt_docs: list[dict] = []
    theme_docs: list[dict] = []
    for ticket_id in ticket_ids:
        idmt_doc, themes = await ingestion.ingest(ticket_id)
        idmt_docs.append(idmt_doc)
        theme_docs.extend(themes)
        gt = idmt_doc["properties"]["themes"]
        print(
            f"{ticket_id}: {len(themes)} linked themes, {len(gt)} resolved VS GT "
            f"({', '.join(t['valueStreamName'] + '=' + t['supportType'] for t in gt) or 'none'})"
        )

    _write(out / "cosmos_idmt.json", idmt_docs)
    _write(out / "cosmos_themes.json", theme_docs)
    print(f"-> {out}/cosmos_idmt.json ({len(idmt_docs)}) + cosmos_themes.json ({len(theme_docs)})")


def _write(path: Path, docs: list[dict]) -> None:
    path.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket_ids", nargs="+")
    parser.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    parser.add_argument("--out", default="out/idmt")
    args = parser.parse_args()
    asyncio.run(main(args.ticket_ids, args.catalogue, args.out))
