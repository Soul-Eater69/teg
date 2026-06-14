"""Why are some GT stages not in the catalogue? (the stage-eval recall ceiling)

The stage eval can only credit a GT stage whose id is in the catalogue the LLM picks from. Some GT
stage ids (from the Epic's Value Stream Stage field) aren't there. This splits the misses by CAUSE
so we know if it's fixable:

  - VS not in catalogue     : the GT value stream id has no catalogue entry at all -> ALL its stages
                              miss (a value-stream id mismatch, not a stage problem)
  - stage missing from VS    : the VS is in the catalogue but this stage id isn't in its list
                              (catalogue incomplete / id mismatch / retired stage)

It lists sample missing stage ids + names so you can eyeball whether they look like valid VSS#####
ids the catalogue just lacks (fixable) vs a different id space (mapping fix). No LLM.

Usage:
  uv run python scripts/diagnose_stage_coverage.py
  uv run python scripts/diagnose_stage_coverage.py --gt out/stage_eval/stage_ground_truth.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from teg.ingestion.catalogues.loader import load_value_stream_catalogue


def main(args: argparse.Namespace) -> None:
    catalogue = load_value_stream_catalogue(args.catalogue)
    vs_stage_ids = {vs.value_stream_id: {s.stage_id for s in vs.stages} for vs in catalogue}
    vs_names = {vs.value_stream_id: vs.value_stream_name for vs in catalogue}

    payload = json.loads(Path(args.gt).read_text(encoding="utf-8"))
    total = present = 0
    vs_absent = 0  # GT stages whose VS isn't in the catalogue at all
    stage_absent = 0  # VS present, stage id missing from its list
    missing_vs: Counter = Counter()  # vs_id -> count of GT stages missed because the VS is absent
    missing_stage_samples: list[tuple[str, str, str]] = []  # (vs_id, stage_id, stage_name)
    vs_in_gt: set[str] = set()
    vs_not_in_cat: set[str] = set()

    for ticket in payload.get("tickets") or []:
        for theme in ticket.get("themes") or []:
            vs_id = theme.get("value_stream_id") or ""
            vs_in_gt.add(vs_id)
            cat_stages = vs_stage_ids.get(vs_id)
            for s in theme.get("stages") or []:
                sid = s.get("stage_id")
                if not sid:
                    continue
                total += 1
                if cat_stages is None:
                    vs_absent += 1
                    vs_not_in_cat.add(vs_id)
                    missing_vs[vs_id] += 1
                elif sid in cat_stages:
                    present += 1
                else:
                    stage_absent += 1
                    if len(missing_stage_samples) < args.samples:
                        missing_stage_samples.append((vs_id, sid, s.get("stage_name") or ""))

    missing = total - present
    print(f"\nGT stages: {total} | in catalogue: {present} ({present/total:.0%}) | "
          f"missing: {missing} ({missing/total:.0%})\n")
    print("MISSING split by cause:")
    print(f"  VS not in catalogue at all : {vs_absent:5}  ({_pct(vs_absent, missing)} of misses)  "
          f"- {len(vs_not_in_cat)} distinct VS ids absent")
    print(f"  stage missing from its VS  : {stage_absent:5}  ({_pct(stage_absent, missing)} of misses)")

    print(f"\nVS ids in GT: {len(vs_in_gt)} | of those NOT in catalogue: {len(vs_not_in_cat)}")
    if missing_vs:
        print("Top absent VS ids (GT stages lost because the whole VS is missing):")
        for vs_id, n in missing_vs.most_common(15):
            print(f"  {n:4}  {vs_id}")

    if missing_stage_samples:
        print(f"\nSample of stages whose VS IS in the catalogue but the stage id is missing:")
        for vs_id, sid, name in missing_stage_samples:
            print(f"  VS {vs_id} ({vs_names.get(vs_id, '?')[:30]}): missing stage {sid}  {name}")

    print("\nREAD: if 'VS not in catalogue' dominates -> a value-stream id mismatch (fix the VS map). "
          "If 'stage missing from its VS' dominates and the ids look like valid VSS##### -> the "
          "catalogue stage list is incomplete for those VS (update the catalogue).")


def _pct(a: int, b: int) -> str:
    return f"{(a / b if b else 0):.0%}"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Diagnose why GT stages aren't in the catalogue.")
    p.add_argument("--gt", default="out/stage_eval/stage_ground_truth.json")
    p.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    p.add_argument("--samples", type=int, default=25)
    main(p.parse_args())
