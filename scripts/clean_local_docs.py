"""One-off: clean text fields in the Cosmos docs already written to disk.

The docs ingested before clean_text was added still hold raw extracted text (control chars,
carriage returns, blank-line runs) in rawText / description. This rewrites those fields in place
using the same clean_text the ingestion now applies, so we don't have to re-fetch from Jira.

    uv run python scripts/clean_local_docs.py                 # default out/idmt
    uv run python scripts/clean_local_docs.py --dir out/idmt --no-backup

Idempotent: re-running on already-clean docs changes nothing. A .bak copy is written by default.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from teg.ingestion.documents.text_cleaning import clean_text

# Doc files and the properties.* text fields to clean in each (missing fields/files are skipped).
_FILES = {
    "cosmos_idmt.json": ("rawText", "description"),
    "cosmos_themes.json": ("description",),
}


def _clean_docs(docs: list[dict], fields: tuple[str, ...]) -> int:
    changed = 0
    for doc in docs:
        props = doc.get("properties") or {}
        for field in fields:
            original = props.get(field)
            if isinstance(original, str) and original:
                cleaned = clean_text(original)
                if cleaned != original:
                    props[field] = cleaned
                    changed += 1
    return changed


def main(out_dir: str, backup: bool) -> None:
    out = Path(out_dir)
    for name, fields in _FILES.items():
        path = out / name
        if not path.exists():
            print(f"skip {path} (not found)")
            continue
        docs = json.loads(path.read_text(encoding="utf-8"))
        if backup:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        changed = _clean_docs(docs, fields)
        path.write_text(json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: cleaned {changed} field(s) across {len(docs)} docs"
              f"{' (backup: ' + path.name + '.bak)' if backup else ''}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="out/idmt", help="directory holding the cosmos_*.json files")
    parser.add_argument("--no-backup", action="store_true", help="do not write a .bak copy first")
    args = parser.parse_args()
    main(args.dir, backup=not args.no_backup)
