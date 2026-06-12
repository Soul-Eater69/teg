"""Rewrite the local cosmos_*.json files into the org Cosmos schema, in place.

Applies the same to_cosmos_doc used at upload (domain=WORKITEM, uppercase entityType / source /
createdBy / lastModifiedBy, drop properties.themes) so the local files match exactly what gets
upserted to Cosmos. Dropping themes from the idmt file is fine: the eval reconstructs ground truth
from the sibling themes file (joining theme.parentRef == er.sourceId).

    uv run python scripts/localize_cosmos_schema.py                 # default out/idmt
    uv run python scripts/localize_cosmos_schema.py --dir out/idmt --no-backup

Idempotent (to_cosmos_doc is idempotent). Writes a .bak copy by default.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from teg.integrations.cosmos import to_cosmos_doc

_FILES = ("cosmos_idmt.json", "cosmos_themes.json")


def main(out_dir: str, backup: bool) -> None:
    out = Path(out_dir)
    for name in _FILES:
        path = out / name
        if not path.exists():
            print(f"skip {path} (not found)")
            continue
        docs = json.loads(path.read_text(encoding="utf-8"))
        if backup:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        docs = [to_cosmos_doc(d) for d in docs]
        path.write_text(json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: rewrote {len(docs)} docs into the Cosmos schema"
              f"{' (backup: ' + path.name + '.bak)' if backup else ''}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="out/idmt", help="directory holding the cosmos_*.json files")
    parser.add_argument("--no-backup", action="store_true", help="do not write a .bak copy first")
    args = parser.parse_args()
    main(args.dir, backup=not args.no_backup)
