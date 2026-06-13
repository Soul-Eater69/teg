"""Token + attachment analysis per IDMT ticket (Tasks 4 & 5) — for the token-budget decisions.

Reads the EDA cache (out/eda/attachments_raw.json, produced by eda_attachments.py) — per-attachment
and per-description token counts (tiktoken), uncapped — and reports what we need to decide:
  - the token distribution of the RAW consolidated text (description + attachments) per ticket,
  - how many tickets would cross a 4k / 8k / 16k / 40k token budget (truncation / latency guardrail),
  - raw vs condense-selected (top-N) token sizes,
  - attachment counts, sizes, types, and tokens per attachment.

    uv run python -m scripts.token_analysis                       # default out/eda/attachments_raw.json
    uv run python -m scripts.token_analysis --cache out/eda/attachments_raw.json

Pure-local (no Jira/Azure/LLM) — it only reads the cache. Run eda_attachments.py first if absent.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

TOKEN_THRESHOLDS = (4_000, 8_000, 16_000, 40_000)


def _pct(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "0%"


def _stats(values: list[float]) -> dict:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {}
    n = len(vals)
    return {"mean": statistics.mean(vals), "median": statistics.median(vals),
            "p90": vals[min(n - 1, int(0.90 * n))], "p95": vals[min(n - 1, int(0.95 * n))],
            "min": vals[0], "max": vals[-1]}


def _line(label: str, s: dict) -> str:
    if not s:
        return f"  {label:24} (no data)"
    return (f"  {label:24} mean {s['mean']:>7.0f}  median {s['median']:>7.0f}  "
            f"p90 {s['p90']:>7.0f}  p95 {s['p95']:>7.0f}  max {s['max']:>7.0f}")


def main(cache_path: str, out_path: str) -> None:
    records = json.loads(Path(cache_path).read_text(encoding="utf-8"))

    # group by ticket
    tickets: dict[str, dict] = {}
    for r in records:
        t = tickets.setdefault(r["ticketId"], {"desc": 0, "attachments": []})
        if r.get("kind") == "description":
            t["desc"] = int(r.get("tokenEst", 0))
        elif r.get("kind") == "attachment" and r.get("supported") and r.get("tokenEst", 0):
            t["attachments"].append(r)

    # --- file sizes (bytes on disk, not tokens) -----------------------------------------------
    def _mb(b: float) -> str:
        return f"{b/1024/1024:.2f} MB" if b >= 1024 * 1024 else f"{b/1024:.0f} KB"

    att_bytes = [int(a.get("sizeBytes", 0)) for t in tickets.values() for a in t["attachments"]]
    ticket_bytes = [sum(int(a.get("sizeBytes", 0)) for a in t["attachments"]) for t in tickets.values()]
    by_type: dict[str, list[int]] = {}
    for t in tickets.values():
        for a in t["attachments"]:
            by_type.setdefault(a.get("ext", "?"), []).append(int(a.get("sizeBytes", 0)))
    print("File sizes on disk (not tokens):")
    sb = _stats(att_bytes)
    print(f"  per attachment   : median {_mb(sb['median'])}  p90 {_mb(sb['p90'])}  "
          f"p95 {_mb(sb['p95'])}  max {_mb(sb['max'])}")
    tb = _stats(ticket_bytes)
    print(f"  per ticket (all) : median {_mb(tb['median'])}  p90 {_mb(tb['p90'])}  max {_mb(tb['max'])}")
    print(f"  avg size by type :  " +
          ",  ".join(f"{ext} {_mb(statistics.mean(v))}" for ext, v in
                     sorted(by_type.items(), key=lambda kv: -len(kv[1]))[:5]))
    print()

    n = len(tickets)
    per_ticket = []
    for tid, t in tickets.items():
        atts = t["attachments"]
        att_tokens = [int(a.get("tokenEst", 0)) for a in atts]
        sel_tokens = [int(a.get("tokenEst", 0)) for a in atts if a.get("selected")]
        per_ticket.append({
            "ticket": tid, "desc_tokens": t["desc"], "n_attachments": len(atts),
            "att_total": sum(att_tokens), "sel_total": sum(sel_tokens),
            "raw_total": t["desc"] + sum(att_tokens),          # description + ALL attachments
            "condense_input": t["desc"] + sum(sel_tokens),     # description + condense-selected
        })

    raw = [p["raw_total"] for p in per_ticket]
    cond = [p["condense_input"] for p in per_ticket]
    no_att = sum(1 for p in per_ticket if p["n_attachments"] == 0)

    print(f"\n=== TOKEN ANALYSIS — {n} tickets (from {cache_path}) ===\n")
    print("Per-ticket token counts (tiktoken):")
    print(_line("description only", _stats([p["desc_tokens"] for p in per_ticket])))
    print(_line("attachments only (all)", _stats([p["att_total"] for p in per_ticket])))
    print(_line("RAW (desc + all attach)", _stats(raw)))
    print(_line("condense input (desc+sel)", _stats(cond)))

    print(f"\nTickets crossing a token budget (on the RAW desc+all-attachments text):")
    for thr in TOKEN_THRESHOLDS:
        over = sum(1 for v in raw if v > thr)
        print(f"  > {thr:>6,} tokens : {over:>4} tickets ({_pct(over, n)})")

    print(f"\nAvg RAW tokens by attachment count (description + all attachments):")
    by_count: dict[int, list[int]] = {}
    for p in per_ticket:
        by_count.setdefault(p["n_attachments"], []).append(p["raw_total"])
    tokens_by_count = {}
    for k in sorted(by_count):
        vals = by_count[k]
        avg = statistics.mean(vals)
        tokens_by_count[k] = round(avg)
        print(f"  {k:>2} attachments : avg {avg:>7.0f} tokens  ({len(vals)} tickets)")

    print(f"\nAttachments (Task 5):")
    counts = Counter(p["n_attachments"] for p in per_ticket)
    print(f"  tickets with NO attachments : {no_att} ({_pct(no_att, n)})")
    print(f"  attachments per ticket      : " + _line("", _stats([p["n_attachments"] for p in per_ticket])).strip())
    all_att = [int(a.get("tokenEst", 0)) for t in tickets.values() for a in t["attachments"]]
    print(f"  tokens per single attachment: " + _line("", _stats(all_att)).strip())
    print(f"  attachment-count histogram  :")
    for k in sorted(counts):
        print(f"     {k:>2} attachments : {counts[k]:>4} tickets")

    # file types
    exts = Counter(a.get("ext", "?") for t in tickets.values() for a in t["attachments"])
    print(f"  top file types              : " +
          ", ".join(f"{e} {c}" for e, c in exts.most_common(8)))

    # raw vs selected (how much condense's top-N keeps)
    keep = statistics.mean(p["condense_input"] / p["raw_total"] for p in per_ticket if p["raw_total"]) if per_ticket else 0
    print(f"\nCondense keeps ~{keep:.0%} of the raw tokens on average (description + selected vs everything).")

    payload = {
        "n_tickets": n, "no_attachment_tickets": no_att,
        "tokens": {"description": _stats([p["desc_tokens"] for p in per_ticket]),
                   "attachments_all": _stats([p["att_total"] for p in per_ticket]),
                   "raw_desc_plus_all": _stats(raw), "condense_input": _stats(cond)},
        "budget_crossings": {str(thr): sum(1 for v in raw if v > thr) for thr in TOKEN_THRESHOLDS},
        "attachments": {"per_ticket": _stats([p["n_attachments"] for p in per_ticket]),
                        "tokens_per_attachment": _stats(all_att),
                        "count_histogram": {str(k): counts[k] for k in sorted(counts)},
                        "avg_raw_tokens_by_count": {str(k): v for k, v in tokens_by_count.items()},
                        "file_types": dict(exts.most_common()),
                        "bytes_per_attachment": _stats(att_bytes),
                        "bytes_per_ticket": _stats(ticket_bytes),
                        "avg_bytes_by_type": {ext: round(statistics.mean(v)) for ext, v in by_type.items()}},
        "condense_keep_ratio": keep,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nsummary -> {out}  (send me this for the write-up)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default="out/eda/attachments/attachments_raw.json",
                        help="EDA cache from eda_attachments.py (per-attachment token records)")
    parser.add_argument("--out", default="out/eda/token_analysis.json")
    args = parser.parse_args()
    main(args.cache, args.out)
