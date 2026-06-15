"""Predict Value Streams from labelled idea cards and compare each against its ground truth.

Reads idea cards from a folder (default ``idea_cards/``), one file per ticket, named with the IDMT id
(e.g. ``IDMT-19761.txt``). For each ticket it:
  1. condenses the idea card and predicts Value Streams, asking for EXACTLY the GT count (so precision
     and recall move together - a fair like-for-like comparison),
  2. compares the prediction to the ground truth, and
  3. prints a per-ticket breakdown built for the SME conversation:
       CAPTURED  - GT we predicted (with the model's reason),
       MISSED    - GT we did NOT predict (with the model's reason for leaving it out),
       EXTRA     - we predicted, GT did NOT have it (with the model's reason) <- the SME talking points:
                   "the model says this applies for THIS reason; your ground truth didn't tag it - why?"

Ground truth is read from a GT json keyed by ticket id (stage_ground_truth.json or cosmos_idmt.json);
only the Value Stream ids/names are used here.

Usage:
  uv run python scripts/compare_idea_cards.py
  uv run python scripts/compare_idea_cards.py --cards idea_cards --gt out/stage_eval/stage_ground_truth.json
  uv run python scripts/compare_idea_cards.py --md out/idea_card_compare.md     # SME-ready markdown
  uv run python scripts/compare_idea_cards.py --json > out/idea_card_compare.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import Field

from teg.bootstrap import build_value_stream_service
from teg.condense.condenser import condense
from teg.condense.models import ResolvedContext
from teg.config.settings import load_settings
from teg.contracts.value_stream_io import ValueStreamRequest
from teg.domain.base import CamelModel
from teg.integrations.files.document_extractor import build_attachment_extractor
from teg.integrations.llm import build_llm_client

_RAW_BUDGET_CHARS = 96_000
_TEXT_EXTS = {".txt", ".md", ".text"}
_DOC_EXTS = {".pdf", ".pptx", ".docx"}        # extracted via DocumentExtractor (same as ingestion)
_CARD_EXTS = _TEXT_EXTS | _DOC_EXTS
_EXTRACTOR = build_attachment_extractor()


def _ticket_id(path: Path) -> str:
    """Filename stem is the IDMT id, e.g. 'IDMT-19761.pdf' -> 'IDMT-19761' (upper-cased)."""
    return path.stem.strip().upper()


def _read_card(path: Path) -> str:
    """Idea-card text: read text files directly; extract .pdf/.pptx/.docx (idea card is the file)."""
    if path.suffix.lower() in _TEXT_EXTS:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    return _EXTRACTOR.extract(path.name, path.read_bytes()).strip()  # .pdf/.pptx/.docx -> text


def _load_cards(folder: str) -> dict[str, str]:
    root = Path(folder)
    if not root.is_dir():
        raise SystemExit(f"idea-cards folder not found: {folder}")
    cards: dict[str, str] = {}
    for p in sorted(root.iterdir()):
        if p.stem.lower() in {"readme", "index", ".ds_store"}:
            continue  # housekeeping files, not idea cards
        if p.suffix.lower() in _CARD_EXTS and p.is_file():
            text = _read_card(p)
            if text:
                cards[_ticket_id(p)] = text[:_RAW_BUDGET_CHARS]
            else:
                print(f"note: no text extracted from {p.name} (empty/image-only/legacy .ppt/.doc) — skipped")
    if not cards:
        raise SystemExit(f"no readable idea cards ({', '.join(sorted(_CARD_EXTS))}) in {folder}")
    return cards


def _load_gt(path: str) -> dict[str, dict[str, str]]:
    """{TICKET_ID: {vs_id: vs_name}} from stage_ground_truth.json (tickets[].themes[]) or
    cosmos_idmt.json (docs[].properties.themes[])."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    if isinstance(payload, dict) and payload.get("tickets"):  # stage_ground_truth.json
        for t in payload["tickets"]:
            tid = (t.get("ticket_id") or "").upper()
            vs = {th.get("value_stream_id"): th.get("value_stream_name") or ""
                  for th in t.get("themes") or [] if th.get("value_stream_id")}
            if tid and vs:
                out[tid] = vs
    else:  # cosmos_idmt.json (list of docs)
        for d in payload if isinstance(payload, list) else payload.get("docs", []):
            tid = (d.get("key") or "").upper()
            vs = {th.get("valueStreamId"): th.get("valueStreamName") or ""
                  for th in (d.get("properties") or {}).get("themes") or [] if th.get("valueStreamId")}
            if tid and vs:
                out[tid] = vs
    return out


class _Rejection(CamelModel):
    value_stream_id: str
    reason: str = ""  # specific, exact wording


class _Rejections(CamelModel):
    rejections: list[_Rejection] = Field(default_factory=list)


_REJECT_SYSTEM = (
    "You explain why specific Value Streams were NOT selected for a ticket. The model has already "
    "picked the Value Streams that best fit this idea card. For EACH not-picked Value Stream listed "
    "(these are in the ground truth but the model did not select them), write ONE precise sentence "
    "giving the EXACT reason it was not selected: name the specific evidence the idea card is MISSING "
    "for it, or name the picked Value Stream that already covers that scope. Be concrete and quote or "
    "paraphrase the idea card - never vague ('not relevant'), never generic. Judge only from the idea "
    "card and the descriptions shown."
)


async def _explain_rejections(idea_card, picked_names, rejected, llm):
    """rejected: list of (vs_id, vs_name, vs_description) -> {vs_id: exact-wording reason}."""
    if not rejected:
        return {}
    blocks = "\n".join(f"- {i} | {n}: {d or '(no description available)'}" for i, n, d in rejected)
    user = (
        f"IDEA CARD:\n{idea_card}\n\n"
        f"PICKED Value Streams: {', '.join(picked_names) or '(none)'}\n\n"
        f"NOT-PICKED Value Streams to explain (give value_stream_id + a specific one-sentence reason):\n"
        f"{blocks}"
    )
    res = await llm.complete(system=_REJECT_SYSTEM, user=user, schema=_Rejections)
    return {r.value_stream_id: r.reason for r in res.rejections if r.reason.strip()}


async def _compare_one(tid, card, gt_vs, *, service, llm, explain):
    """Predict at GT count, diff against GT, and (optionally) explain the misses."""
    context = ResolvedContext(ticket_id=tid, ticket_title="", description="",
                              primary_source="idea_card", attachments_used=[], consolidated_text=card)
    condensed = await condense(context, llm)
    request = ValueStreamRequest(ticket_id=tid, summary_fields=condensed.summary_fields,
                                 prompt_text=condensed.raw_text, requested_count=len(gt_vs))
    response, trace = await service.predict_traced(request)

    # Hard-cap to the GT count: take the top-ranked len(gt) picks so prediction count == GT length.
    recs = response.recommendations[:len(gt_vs)]
    pred = {r.value_stream_id: r for r in recs}
    captured = [(i, n) for i, n in gt_vs.items() if i in pred]      # GT we got
    missed = [(i, n) for i, n in gt_vs.items() if i not in pred]    # GT we didn't get
    extra = [(i, r) for i, r in pred.items() if i not in gt_vs]     # picked, not in GT

    # Exact-wording reason each rejected GT was not selected (one focused LLM call).
    miss_reasons: dict[str, str] = {}
    if explain and missed:
        desc = {c.value_stream_id: c.value_stream_description for c in trace.review_pool}
        rejected = [(i, n, desc.get(i, "")) for i, n in missed]
        picked_names = [r.value_stream_name for r in recs]
        miss_reasons = await _explain_rejections(condensed.raw_text, picked_names, rejected, llm)

    return {
        "ticket_id": tid,
        "gt_count": len(gt_vs),
        "captured": [{"id": i, "name": n, "reason": pred[i].reason} for i, n in captured],
        "missed": [{"id": i, "name": n, "reason": miss_reasons.get(i, "not selected at GT count")}
                   for i, n in missed],
        "extra": [{"id": i, "name": r.value_stream_name, "confidence": r.confidence,
                   "support": r.support_type, "reason": r.reason} for i, r in extra],
    }


def _md_report(rows: list[dict]) -> str:
    """A clean SME-facing markdown report: summary table + per-ticket captured/missed/extra."""
    tot_gt = sum(r["gt_count"] for r in rows)
    tot_cap = sum(len(r["captured"]) for r in rows)
    tot_extra = sum(len(r["extra"]) for r in rows)
    out: list[str] = []
    out.append("# Idea-card Value Stream predictions vs ground truth\n")
    out.append("Each ticket is predicted at its **ground-truth Value Stream count** (like-for-like). "
               "**Extra** = the model predicted it but the ground truth did not have it — the items to "
               "review with the SME.\n")

    # summary table
    out.append("## Summary\n")
    out.append("| ticket | GT | captured | missed | extra | recall |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for r in rows:
        cap, gtc = len(r["captured"]), r["gt_count"]
        out.append(f"| {r['ticket_id']} | {gtc} | {cap} | {len(r['missed'])} | "
                   f"{len(r['extra'])} | {cap/gtc:.0%} |" if gtc else
                   f"| {r['ticket_id']} | 0 | {cap} | {len(r['missed'])} | {len(r['extra'])} | – |")
    out.append(f"| **total** | **{tot_gt}** | **{tot_cap}** | **{tot_gt - tot_cap}** | "
               f"**{tot_extra}** | **{tot_cap/tot_gt:.0%}** |" if tot_gt else "")

    # per-ticket detail
    for r in rows:
        cap, miss, extra, gtc = r["captured"], r["missed"], r["extra"], r["gt_count"]
        recall = len(cap) / gtc if gtc else 1.0
        out.append(f"\n---\n\n## {r['ticket_id']}\n")
        out.append(f"GT **{gtc}** · captured **{len(cap)}** · missed **{len(miss)}** · "
                   f"extra **{len(extra)}** · recall **{recall:.0%}**\n")

        out.append(f"### ✓ Captured ({len(cap)}) — GT the model predicted")
        out.append("\n".join(f"- **{c['name']}** — {c['reason']}" for c in cap) or "_none_")

        out.append(f"\n### ✗ Missed ({len(miss)}) — GT the model did not predict")
        out.append("\n".join(f"- **{m['name']}** — _why left out:_ {m['reason']}" for m in miss) or "_none_")

        out.append(f"\n### ➕ Extra ({len(extra)}) — model predicted, NOT in GT → review with SME")
        out.append("\n".join(
            f"- **{e['name']}** ({e['confidence']:.0f}%, {e['support']}) — _why picked:_ {e['reason']}"
            for e in extra) or "_none_")
    return "\n".join(out) + "\n"


def _print_report(rows: list[dict]) -> None:
    tot_gt = tot_cap = tot_extra = 0
    for r in rows:
        cap, miss, extra = r["captured"], r["missed"], r["extra"]
        tot_gt += r["gt_count"]; tot_cap += len(cap); tot_extra += len(extra)
        recall = len(cap) / r["gt_count"] if r["gt_count"] else 1.0
        print(f"\n{'='*100}\n{r['ticket_id']}   GT={r['gt_count']}  captured={len(cap)}  "
              f"missed={len(miss)}  extra={len(extra)}  recall={recall:.0%}\n{'='*100}")
        print(f"\n  CAPTURED ({len(cap)})  — GT the model predicted:")
        for c in cap or [{"name": "—", "reason": ""}]:
            print(f"    ✓ {c['name']}\n        why: {c['reason']}")
        print(f"\n  MISSED ({len(miss)})  — GT the model did NOT predict:")
        for m in miss or [{"name": "—", "reason": ""}]:
            print(f"    ✗ {m['name']}\n        why left out: {m['reason']}")
        print(f"\n  EXTRA ({len(extra)})  — model predicted, NOT in GT  (take to SME):")
        for e in extra or [{"name": "—", "confidence": 0, "support": "", "reason": ""}]:
            print(f"    + {e['name']}  ({e['confidence']:.0f}%, {e['support']})\n        why picked: {e['reason']}")
    n = len(rows)
    print(f"\n{'#'*100}\nSUMMARY  ({n} tickets)\n{'#'*100}")
    print(f"  total GT value streams : {tot_gt}")
    print(f"  captured               : {tot_cap}  ({tot_cap/tot_gt:.0%} recall)" if tot_gt else "  captured: 0")
    print(f"  missed                 : {tot_gt - tot_cap}")
    print(f"  extra (not in GT)      : {tot_extra}   ← the 'why isn't this in your GT?' list for the SME")


async def main(args: argparse.Namespace) -> None:
    cards = _load_cards(args.cards)
    gt = _load_gt(args.gt)
    settings = load_settings()
    service = build_value_stream_service(settings)
    llm = build_llm_client(settings)

    targets = [t for t in cards if t in gt]
    skipped = [t for t in cards if t not in gt]
    if skipped:
        print(f"note: no GT for {len(skipped)} card(s), skipped: {', '.join(skipped)}")
    if not targets:
        raise SystemExit("no idea cards matched a ground-truth ticket id")

    try:
        rows = await asyncio.gather(*(
            _compare_one(t, cards[t], gt[t], service=service, llm=llm, explain=not args.no_explain)
            for t in targets))
    finally:
        await service.aclose()  # close the search + selection-LLM sessions
        await llm.aclose()      # close the condense/explain LLM session

    if args.md:
        Path(args.md).write_text(_md_report(rows), encoding="utf-8")
        print(f"wrote markdown report -> {args.md}")
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    elif not args.md:
        _print_report(rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Compare idea-card VS predictions against ground truth.")
    p.add_argument("--cards", default="idea_cards", help="folder of idea-card files (default idea_cards/)")
    p.add_argument("--gt", default="out/stage_eval/stage_ground_truth.json", help="ground-truth json")
    p.add_argument("--no-explain", action="store_true", help="skip the LLM 'why missed' explanation pass")
    p.add_argument("--md", default="", help="write the report to this markdown file (e.g. out/idea_card_compare.md)")
    p.add_argument("--json", action="store_true", help="emit structured JSON instead of the report")
    asyncio.run(main(p.parse_args()))
