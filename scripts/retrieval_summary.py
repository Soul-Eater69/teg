"""Extract the compact summary from an already-generated retrieval_eval.json.

The full json has a huge per_query block. This pulls out just config + aggregates + examples (~200
lines) so it can be sent for the write-up - no need to re-run the eval.

    uv run python scripts/retrieval_summary.py out/eval/retrieval_eval.json
    -> writes out/eval/retrieval_eval_summary.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "out/eval/retrieval_eval.json")
    payload = json.loads(src.read_text(encoding="utf-8"))
    summary = {k: payload[k] for k in ("config", "aggregates", "examples") if k in payload}
    out = src.with_name(src.stem + "_summary.json")
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"summary -> {out}  ({len(out.read_text().splitlines())} lines)")


if __name__ == "__main__":
    main()
