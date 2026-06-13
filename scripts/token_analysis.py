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

TOKEN_THRESHOLDS = (5_000, 10_000, 15_000, 20_000, 25_000, 30_000)


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


def _hist(values: list[float], bins: list[tuple]) -> dict:
    """Bin values into labelled ranges -> {label: count}, so the json carries chart-ready histograms."""
    out = {label: 0 for _, _, label in bins}
    for v in values:
        for lo, hi, label in bins:
            if lo <= v < hi:
                out[label] += 1
                break
    return out


_MB = 1024 * 1024
TOKEN_BINS_TICKET = [(0, 2000, "0-2k"), (2000, 4000, "2-4k"), (4000, 8000, "4-8k"),
                     (8000, 16000, "8-16k"), (16000, 32000, "16-32k"), (32000, float("inf"), "32k+")]
TOKEN_BINS_ATT = [(0, 1000, "0-1k"), (1000, 2000, "1-2k"), (2000, 4000, "2-4k"),
                  (4000, 8000, "4-8k"), (8000, 16000, "8-16k"), (16000, float("inf"), "16k+")]
BYTE_BINS = [(0, 100 * 1024, "<100KB"), (100 * 1024, 500 * 1024, "100-500KB"),
             (500 * 1024, _MB, "0.5-1MB"), (_MB, 2 * _MB, "1-2MB"),
             (2 * _MB, 5 * _MB, "2-5MB"), (5 * _MB, float("inf"), "5MB+")]


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

    print(f"\nTokens per ticket vs budget (RAW desc+all-attachments text):")
    for thr in TOKEN_THRESHOLDS:
        fit = sum(1 for v in raw if v <= thr)
        print(f"  <= {thr:>6,} tokens : {fit:>4} tickets fit ({_pct(fit, n)})   "
              f"[{n - fit} over]")

    # For the RETRIEVAL-embedding question: if we truncate every ticket's raw text at a budget,
    # how much of the TOTAL content (across all tickets) is kept, and how many tickets are untouched.
    total_raw = sum(raw)
    print(f"\nContent kept if we TRUNCATE every ticket's raw text (for the embedding):")
    for b in (5_000, 7_000, 7_500, 10_000, 15_000):
        captured = sum(min(v, b) for v in raw)
        untouched = sum(1 for v in raw if v <= b)
        print(f"  truncate @ {b:>6,} : {captured/total_raw:>4.0%} of all content kept   "
              f"({_pct(untouched, n)} tickets untouched)")

    # CHUNKING alternative (multi-vector, no content loss): 1 chunk per description + per attachment,
    # sub-chunk any attachment over the embedding limit. How many vectors does that cost?
    import math
    embed_limit = 7_500  # ~30k-char embedding cap
    att_toks = [int(a.get("tokenEst", 0)) for t in tickets.values() for a in t["attachments"]]
    n_desc = sum(1 for t in tickets.values() if t["desc"])
    under = sum(1 for v in att_toks if v <= embed_limit)
    over = [v for v in att_toks if v > embed_limit]
    sub = sum(math.ceil(v / embed_limit) for v in over)
    total_chunks = n_desc + under + sub
    print(f"\nChunking (1 vector per description + per attachment; sub-chunk if > {embed_limit:,} tokens):")
    print(f"  attachments that fit one vector : {under}/{len(att_toks)} ({_pct(under, len(att_toks))})")
    print(f"  attachments needing sub-chunks  : {len(over)} ({_pct(len(over), len(att_toks))})")
    print(f"  total vectors in the index      : ~{total_chunks} (vs {n} single-vector = {total_chunks/n:.1f}x)")
    print(f"  -> captures 100% of content, no summarization, each chunk fully embeddable")

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

    # --- full EDA: distributions, per-type detail, extraction health, idea cards ---------------
    all_att_recs = [r for r in records if r.get("kind") == "attachment"]
    n_att_total = len(all_att_recs)
    supported = [r for r in all_att_recs if r.get("supported")]
    with_text = [r for r in supported if r.get("tokenEst", 0)]
    failed = [r for r in all_att_recs if r.get("extractError")]
    empty = [r for r in supported if not r.get("tokenEst", 0) and not r.get("extractError")]
    idea_tickets = {r["ticketId"] for r in all_att_recs if r.get("ideaCard")}

    # per-type detail: count, avg tokens, avg MB, extraction density (tokens per MB)
    type_detail = {}
    by_type_tokens: dict[str, list[int]] = {}
    by_type_bytes: dict[str, list[int]] = {}
    for r in with_text:
        e = r.get("ext", "?")
        by_type_tokens.setdefault(e, []).append(int(r.get("tokenEst", 0)))
        by_type_bytes.setdefault(e, []).append(int(r.get("sizeBytes", 0)))
    for e in by_type_tokens:
        toks, byts = by_type_tokens[e], by_type_bytes[e]
        avg_mb = (statistics.mean(byts) / _MB) if byts else 0
        type_detail[e] = {"count": len(toks), "avg_tokens": round(statistics.mean(toks)),
                          "avg_mb": round(avg_mb, 2),
                          "tokens_per_mb": round(statistics.mean(toks) / avg_mb) if avg_mb else None}

    print(f"\nExtraction health: {n_att_total} attachments | {len(supported)} supported | "
          f"{len(with_text)} extracted text | {len(failed)} failed | {len(empty)} empty (e.g. image)")
    print(f"Idea-card attachment present in {len(idea_tickets)} tickets ({_pct(len(idea_tickets), n)})")
    print(f"Tokens per MB by type (extraction density): " +
          ", ".join(f"{e} {d['tokens_per_mb']}" for e, d in
                    sorted(type_detail.items(), key=lambda kv: -kv[1]['count']) if d['tokens_per_mb']))

    payload = {
        "n_tickets": n, "no_attachment_tickets": no_att,
        "tokens": {"description": _stats([p["desc_tokens"] for p in per_ticket]),
                   "attachments_all": _stats([p["att_total"] for p in per_ticket]),
                   "raw_desc_plus_all": _stats(raw), "condense_input": _stats(cond)},
        "budget_crossings": {str(thr): sum(1 for v in raw if v > thr) for thr in TOKEN_THRESHOLDS},
        "distributions": {
            "raw_tokens_per_ticket": _hist(raw, TOKEN_BINS_TICKET),
            "attachment_text_per_ticket": _hist([p["att_total"] for p in per_ticket], TOKEN_BINS_TICKET),
            "tokens_per_attachment": _hist(all_att, TOKEN_BINS_ATT),
            "bytes_per_attachment": _hist(att_bytes, BYTE_BINS),
            "bytes_per_ticket": _hist(ticket_bytes, BYTE_BINS),
        },
        "attachments": {"per_ticket": _stats([p["n_attachments"] for p in per_ticket]),
                        "tokens_per_attachment": _stats(all_att),
                        "count_histogram": {str(k): counts[k] for k in sorted(counts)},
                        "avg_raw_tokens_by_count": {str(k): v for k, v in tokens_by_count.items()},
                        "file_types": dict(exts.most_common()),
                        "bytes_per_attachment": _stats(att_bytes),
                        "bytes_per_ticket": _stats(ticket_bytes),
                        "avg_bytes_by_type": {ext: round(statistics.mean(v)) for ext, v in by_type.items()},
                        "type_detail": type_detail},
        "extraction_health": {"total": n_att_total, "supported": len(supported),
                              "extracted_text": len(with_text), "failed": len(failed),
                              "empty_no_text": len(empty), "idea_card_tickets": len(idea_tickets)},
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
