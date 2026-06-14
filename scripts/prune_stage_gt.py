"""Remove uncatalogued GT stages from an existing stage_ground_truth.json (no Jira re-extract).

The diagnosis showed ~18% of GT stages have a valid VSS id that isn't in the approved catalogue for
their VS (retired / out-of-catalogue stages the model can't pick). This rewrites the existing GT
file in place, dropping those stages so eval coverage is 100% and recall/precision score only
answerable GT. Writes a .bak first.

Usage:
  uv run python scripts/prune_stage_gt.py
  uv run python scripts/prune_stage_gt.py --gt out/stage_eval/stage_ground_truth.json --no-backup
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from teg.ingestion.catalogues.loader import load_value_stream_catalogue


def main(args: argparse.Namespace) -> None:
    catalogue = load_value_stream_catalogue(args.catalogue)
    allowed = {vs.value_stream_id: {s.stage_id for s in vs.stages} for vs in catalogue}

    path = Path(args.gt)
    payload = json.loads(path.read_text(encoding="utf-8"))
    kept = dropped = 0
    for ticket in payload.get("tickets") or []:
        for theme in ticket.get("themes") or []:
            cat = allowed.get(theme.get("value_stream_id") or "", set())
            stages = theme.get("stages") or []
            keep = [s for s in stages if s.get("stage_id") in cat]
            dropped += len(stages) - len(keep)
            kept += len(keep)
            theme["stages"] = keep

    if args.backup:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Keep the sibling .jsonl in sync if present.
    jsonl = path.with_suffix(".jsonl")
    if jsonl.exists():
        with jsonl.open("w", encoding="utf-8") as fh:
            for ticket in payload.get("tickets") or []:
                fh.write(json.dumps(ticket, ensure_ascii=False) + "\n")

    total = kept + dropped
    print(f"{path.name}: kept {kept}/{total} GT stages, dropped {dropped} "
          f"({(dropped/total if total else 0):.0%}) not in the approved catalogue"
          + (f"  (backup: {path.name}.bak)" if args.backup else ""))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Prune uncatalogued stages from an existing GT file.")
    p.add_argument("--gt", default="out/stage_eval/stage_ground_truth.json")
    p.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    p.add_argument("--no-backup", dest="backup", action="store_false")
    main(p.parse_args())
