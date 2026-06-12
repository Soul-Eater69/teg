"""Historic-lane retrieval evaluation - the precedent retriever, measured on its own.

The historic lane retrieves the top-K similar past tickets shown to the model as precedent. This
evaluates that retriever WITHOUT the LLM, using a free, automatic relevance signal: every past
ticket carries its own Value Stream labels, so a retrieved ticket is RELEVANT to the query when its
labels overlap the query's GT Value Streams. That single definition makes the classic IR metrics
apply (recall@k, precision@k, MRR, nDCG, hit@k) - no human/LLM relevance labels needed.

It retrieves the top (max-K) ONCE per ticket and slices for K=6/8/10 (one search call each), so the
whole sweep is one pass. It dumps a COMPLETE json (every per-query record + all aggregates) so the
write-up can be drafted from the data without re-running, and builds a charted docx.

    uv sync --extra search --extra eda --extra extract
    uv run python -m scripts.retrieval_eval out/idmt/cosmos_idmt.json --min-gt 1

Needs the Search env + the historic (EngagementRequest) docs in the index (VPN if dev). No LLM
chat calls - only the query embedding + the search.

Definitions (relevance = the query's GT VS overlapping a retrieved ticket's VS labels):
  recall@k / coverage  of the query's GT VS, the fraction present in the union of the top-K tickets
  precision@k          of the K retrieved tickets, the fraction that are relevant (share a GT VS)
  hit@k                1 if >=1 relevant ticket is in the top-K
  MRR                  1 / rank of the first relevant retrieved ticket
  nDCG@k               rank-weighted relevance (rewards relevant tickets ranked higher)
  evidence density     VS labels carried per retrieved ticket
  context usage        (carried from the generation eval) of GT put IN context, how much the model used
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import statistics
from collections import Counter
from pathlib import Path
from time import perf_counter

from scripts.eval_vs import _gt_ids, _load, _summary_fields

from teg.config.settings import load_settings
from teg.integrations.llm import build_llm_client
from teg.integrations.search import build_search_client
from teg.value_stream.content_relevance_judge import judge_ticket_relevance
from teg.value_stream.retrieval import build_retrieval_text

K_VALUES = (6, 8, 10)
MAX_K = max(K_VALUES)
OVERFETCH = 3  # over-fetch so dropping the ticket itself still leaves MAX_K analogs
BROAD_FRACTION = 0.15  # a VS tagged on >15% of tickets is "broad" (precision_strict ignores it)


# ----------------------------------------------------------------- per-query retrieval

async def _eval_one(doc, search, gt: set[str], *, llm=None, content_by_key=None) -> dict:
    key = doc.get("key") or ""
    summary = _summary_fields(doc.get("properties", {}), raw_text=False)
    query = build_retrieval_text(summary)
    hits = await search.search_historical(query, top_k=MAX_K + OVERFETCH)
    # Drop the ticket itself, keep the top MAX_K (one retrieval, then slice for each K).
    hits = [h for h in hits if h.ticket_id != key][:MAX_K]

    # Content-relevance judge (diagnostic): one batched LLM call judging all retrieved tickets.
    # Use the richer local doc content where available, else the search snippet.
    content = content_by_key or {}
    judged: dict[str, bool] = {}
    if llm is not None and hits:
        tickets = [(h.ticket_id, (content.get(h.ticket_id) or h.snippet or "")[:1200]) for h in hits]
        try:
            judged = await judge_ticket_relevance(query=query[:4000], tickets=tickets, llm_client=llm)
        except Exception as exc:
            print(f"    judge failed for {key}: {type(exc).__name__}: {exc}")

    retrieved = []
    for rank, h in enumerate(hits, start=1):
        vs_ids = sorted({v.value_stream_id for v in h.value_streams if v.value_stream_id})
        shown = (content.get(h.ticket_id) or h.snippet or "").replace("\n", " ").strip()
        retrieved.append({
            "rank": rank, "ticket_id": h.ticket_id, "score": round(h.score, 4),
            "vs_ids": vs_ids, "vs_names": [v.value_stream_name for v in h.value_streams if v.value_stream_id],
            "n_vs": len(vs_ids), "text": shown[:280],  # the content shown (for example write-ups)
            "relevant": bool(set(vs_ids) & gt),  # label-relevance (primary)
            "content_relevant": judged.get(h.ticket_id) if judged else None,  # content-relevance (diagnostic)
        })

    at_k = {}
    for k in K_VALUES:
        top = retrieved[:k]
        covered = {v for r in top for v in r["vs_ids"]} & gt
        rel_ranks = [r["rank"] for r in top if r["relevant"]]
        n_rel = len(rel_ranks)
        n_content = sum(1 for r in top if r["content_relevant"]) if judged else None
        dcg = sum(1.0 / math.log2(r["rank"] + 1) for r in top if r["relevant"])
        ideal = sum(1.0 / math.log2(i + 2) for i in range(min(n_rel, k)))
        at_k[k] = {
            "recall": len(covered) / len(gt) if gt else 0.0,
            "coverage_count": len(covered),
            "precision": n_rel / len(top) if top else 0.0,
            "n_relevant": n_rel,
            "hit": 1 if n_rel else 0,
            "rr": 1.0 / rel_ranks[0] if rel_ranks else 0.0,
            "ndcg": dcg / ideal if ideal else 0.0,
            "evidence_density": statistics.mean(r["n_vs"] for r in top) if top else 0.0,
            "content_precision": (n_content / len(top)) if (judged and top) else None,
            "content_hit": (1 if n_content else 0) if judged else None,
        }
    first_rel = next((r["rank"] for r in retrieved if r["relevant"]), None)
    return {
        "ticket_id": key, "gt_size": len(gt), "n_retrieved": len(retrieved),
        "first_relevant_rank": first_rel, "retrieved": retrieved, "at_k": at_k,
    }


# ----------------------------------------------------------------- aggregation

def _stats(values: list[float]) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {"mean": statistics.mean(vals), "median": statistics.median(vals),
            "min": min(vals), "max": max(vals)}


def _aggregate(per_query: list[dict], broad: set[str], gt_by_ticket: dict[str, set]) -> dict:
    n = len(per_query)
    by_k = {}
    for k in K_VALUES:
        rec = [q["at_k"][k]["recall"] for q in per_query]
        prec = [q["at_k"][k]["precision"] for q in per_query]
        # precision_strict: relevant only via a NON-broad shared VS
        strict = []
        for q in per_query:
            gt = gt_by_ticket[q["ticket_id"]]
            top = q["retrieved"][:k]
            n_strict = sum(1 for r in top if (set(r["vs_ids"]) & gt) - broad)
            strict.append(n_strict / len(top) if top else 0.0)
        cprec = [q["at_k"][k]["content_precision"] for q in per_query
                 if q["at_k"][k]["content_precision"] is not None]
        chit = [q["at_k"][k]["content_hit"] for q in per_query if q["at_k"][k]["content_hit"] is not None]
        by_k[k] = {
            "recall": _stats(rec),
            "precision": _stats(prec),
            "precision_strict": _stats(strict),
            "content_precision": _stats(cprec) if cprec else {"mean": None},
            "content_hit_rate": (statistics.mean(chit) if chit else None),
            "hit_rate": statistics.mean(q["at_k"][k]["hit"] for q in per_query),
            "mrr": statistics.mean(q["at_k"][k]["rr"] for q in per_query),
            "ndcg": statistics.mean(q["at_k"][k]["ndcg"] for q in per_query),
            "evidence_density": _stats([q["at_k"][k]["evidence_density"] for q in per_query]),
            "fully_covered_rate": statistics.mean(1 if q["at_k"][k]["recall"] >= 0.999 else 0 for q in per_query),
            "zero_hit_rate": statistics.mean(1 if q["at_k"][k]["hit"] == 0 else 0 for q in per_query),
            "mean_relevant": statistics.mean(q["at_k"][k]["n_relevant"] for q in per_query),
        }
    # marginal gain/loss going up in K
    marginal = {}
    for a, b in ((6, 8), (8, 10)):
        marginal[f"{a}->{b}"] = {
            "recall_gain": by_k[b]["recall"]["mean"] - by_k[a]["recall"]["mean"],
            "precision_change": by_k[b]["precision"]["mean"] - by_k[a]["precision"]["mean"],
        }
    # evidence density over EVERY retrieved ticket (at max K)
    all_nvs = [r["n_vs"] for q in per_query for r in q["retrieved"]]
    # score separation: relevant vs irrelevant retrieved-ticket scores
    rel_scores = [r["score"] for q in per_query for r in q["retrieved"] if r["relevant"]]
    irr_scores = [r["score"] for q in per_query for r in q["retrieved"] if not r["relevant"]]
    first_ranks = [q["first_relevant_rank"] for q in per_query if q["first_relevant_rank"]]
    # label x content cross-tab over every retrieved ticket that was judged (the diagnostic)
    crosstab = None
    judged_rows = [r for q in per_query for r in q["retrieved"] if r.get("content_relevant") is not None]
    if judged_rows:
        crosstab = {
            "label_and_content": sum(1 for r in judged_rows if r["relevant"] and r["content_relevant"]),
            "label_not_content": sum(1 for r in judged_rows if r["relevant"] and not r["content_relevant"]),
            "content_not_label": sum(1 for r in judged_rows if not r["relevant"] and r["content_relevant"]),
            "neither": sum(1 for r in judged_rows if not r["relevant"] and not r["content_relevant"]),
            "total_judged": len(judged_rows),
        }
    return {
        "n_queries": n,
        "by_k": by_k,
        "marginal": marginal,
        "gt_size": _stats([q["gt_size"] for q in per_query]),
        "n_retrieved": _stats([q["n_retrieved"] for q in per_query]),
        "evidence_density_all": {**_stats(all_nvs),
                                 "histogram": dict(sorted(Counter(all_nvs).items()))},
        "first_relevant_rank": {**_stats(first_ranks),
                                "histogram": dict(sorted(Counter(first_ranks).items())),
                                "none_count": sum(1 for q in per_query if not q["first_relevant_rank"])},
        "score_separation": {"relevant_mean": _stats(rel_scores)["mean"],
                             "irrelevant_mean": _stats(irr_scores)["mean"],
                             "relevant_n": len(rel_scores), "irrelevant_n": len(irr_scores)},
        "broad_streams": sorted(broad),
        "label_vs_content": crosstab,
    }


# ----------------------------------------------------------------- run

async def run(args) -> dict:
    docs = _load(args.dataset)
    gt_by_ticket = {d.get("key", ""): _gt_ids(d.get("properties", {})) for d in docs}
    docs = [d for d in docs if len(gt_by_ticket.get(d.get("key", ""), set())) >= args.min_gt]
    if args.sample:
        random.seed(args.seed)
        docs = random.sample(docs, min(args.sample, len(docs)))
    print(f"retrieval eval over {len(docs)} tickets (min_gt={args.min_gt}); K={K_VALUES}")

    # corpus VS frequency -> broad streams (tagged on >BROAD_FRACTION of tickets)
    freq = Counter(vs for d in docs for vs in gt_by_ticket[d.get("key", "")])
    n = len(docs)
    broad = {vs for vs, c in freq.items() if n and c / n > BROAD_FRACTION}

    settings = load_settings()
    search = build_search_client(settings)
    llm = build_llm_client(settings) if args.judge else None
    # Map each ticket key -> its local businessSummary (else rawText): the judge's content + the text
    # used in the example write-ups. Built for all docs (not just when judging).
    content_by_key, vs_names = {}, {}
    for d in _load(args.dataset):
        p = d.get("properties", {})
        content_by_key[d.get("key", "")] = (p.get("businessSummary") or (p.get("rawText") or ""))[:1200]
        for t in p.get("themes") or []:
            if t.get("valueStreamId"):
                vs_names[t["valueStreamId"]] = t.get("valueStreamName") or t["valueStreamId"]
    sem = asyncio.Semaphore(args.concurrency)
    total = len(docs)
    done = 0

    async def _guarded(d):
        nonlocal done
        async with sem:
            gt = gt_by_ticket[d.get("key", "")]
            t0 = perf_counter()
            try:
                res = await _eval_one(d, search, gt, llm=llm, content_by_key=content_by_key)
            except Exception as exc:  # keep the run alive; record the failure
                done += 1
                print(f"  [{done}/{total}] {d.get('key')} FAILED: {type(exc).__name__}: {exc}")
                return None
            done += 1
            rel = res["at_k"][MAX_K]["n_relevant"]
            cov = res["at_k"][MAX_K]["recall"]
            print(f"  [{done}/{total}] {res['ticket_id']:<14} {perf_counter() - t0:5.1f}s  "
                  f"relevant@{MAX_K}={rel} coverage={cov:.0%}" + ("  judged" if llm else ""))
            return res

    results = await asyncio.gather(*(_guarded(d) for d in docs))
    close = getattr(search, "close", None)
    if close:
        await close()
    per_query = [r for r in results if r]
    if not per_query:
        raise SystemExit("no tickets evaluated (check the index has EngagementRequest docs + creds)")

    aggregates = _aggregate(per_query, broad, gt_by_ticket)
    payload = {
        "config": {"dataset": args.dataset, "k_values": list(K_VALUES), "max_k": MAX_K,
                   "min_gt": args.min_gt, "broad_fraction": BROAD_FRACTION,
                   "relevance": "query GT VS overlaps a retrieved ticket's VS labels"},
        "aggregates": aggregates,
        "examples": _examples(per_query, gt_by_ticket, content_by_key, vs_names),  # concrete cases
        "per_query": per_query,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Compact summary (no per_query) - small enough to send for the write-up.
    summary = {k: payload[k] for k in ("config", "aggregates", "examples")}
    summary_path = out.with_name(out.stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\ncomplete data -> {out}")
    print(f"compact summary -> {summary_path}  (~send me THIS one)")
    _print_summary(aggregates)
    print(f"\nSend me {summary_path.name} (the compact one, no per-query dump) and I'll draft the write-up.")
    return payload


def _examples(per_query: list[dict], gt_by_ticket: dict[str, set],
              content: dict[str, str], vs_names: dict[str, str], cap: int = 6) -> dict:
    """Concrete cases WITH text so the write-up can cite real tickets (can't be recovered post-run)."""
    def gt_named(tid):
        return [f"{v} ({vs_names.get(v, v)})" for v in sorted(gt_by_ticket.get(tid, []))]

    def case(q, r):
        return {
            "query_ticket": q["ticket_id"],
            "query_text": (content.get(q["ticket_id"], "") or "")[:280],
            "query_gt": gt_named(q["ticket_id"]),
            "retrieved_ticket": r["ticket_id"], "rank": r["rank"], "score": r["score"],
            "retrieved_text": r.get("text", ""),
            "retrieved_vs": [f"{i} ({n})" for i, n in zip(r["vs_ids"], r.get("vs_names", []))] or r["vs_ids"],
            "shared_vs": sorted(set(r["vs_ids"]) & gt_by_ticket.get(q["ticket_id"], set())),
            "label_relevant": r["relevant"], "content_relevant": r["content_relevant"],
        }
    lucky, mislabeled = [], []
    for q in per_query:
        for r in q["retrieved"]:
            if r.get("content_relevant") is None:
                continue
            if r["relevant"] and not r["content_relevant"] and len(lucky) < cap:
                lucky.append(case(q, r))            # shares a VS but not the same change
            if not r["relevant"] and r["content_relevant"] and len(mislabeled) < cap:
                mislabeled.append(case(q, r))        # same change but different label
    fully = [{"ticket": q["ticket_id"], "gt": gt_named(q["ticket_id"])}
             for q in per_query if q["at_k"][MAX_K]["recall"] >= 0.999][:cap]
    zero = [{"ticket": q["ticket_id"], "gt": gt_named(q["ticket_id"]),
             "query_text": (content.get(q["ticket_id"], "") or "")[:280]}
            for q in per_query if q["at_k"][MAX_K]["hit"] == 0][:cap]
    return {"lucky_label_matches": lucky, "content_not_label": mislabeled,
            "fully_covered_tickets": fully, "zero_relevant_tickets": zero}


def _print_summary(agg: dict) -> None:
    print(f"\n{'K':>4}  {'recall':>8} {'prec':>7} {'prec*':>7} {'hit':>6} {'MRR':>6} {'nDCG':>6} "
          f"{'zeroHit':>8} {'fullCov':>8}")
    for k in K_VALUES:
        b = agg["by_k"][k]
        print(f"{k:>4}  {b['recall']['mean']:>8.3f} {b['precision']['mean']:>7.3f} "
              f"{b['precision_strict']['mean']:>7.3f} {b['hit_rate']:>6.3f} {b['mrr']:>6.3f} "
              f"{b['ndcg']:>6.3f} {b['zero_hit_rate']:>8.3f} {b['fully_covered_rate']:>8.3f}")
    s = agg["score_separation"]
    _f = lambda v: "n/a" if v is None else f"{v:.3f}"  # noqa: E731
    print(f"\nscore separation: relevant {_f(s['relevant_mean'])} vs irrelevant {_f(s['irrelevant_mean'])}")
    print(f"evidence density (VS/ticket): mean {agg['evidence_density_all']['mean']:.2f} "
          f"(min {agg['evidence_density_all']['min']}, max {agg['evidence_density_all']['max']})")
    fr = agg["first_relevant_rank"]
    print(f"first relevant at rank: median {fr['median']} (none for {fr['none_count']} queries)")
    ct = agg.get("label_vs_content")
    if ct:
        tot = ct["total_judged"]
        print(f"\nlabel vs content (judged {tot} retrieved tickets):")
        print(f"  label+content (real hit) : {ct['label_and_content']:>4} ({ct['label_and_content']/tot:.0%})")
        print(f"  label, NOT content (lucky): {ct['label_not_content']:>4} ({ct['label_not_content']/tot:.0%})")
        print(f"  content, NOT label (mislabeled): {ct['content_not_label']:>4} ({ct['content_not_label']/tot:.0%})")
        print(f"  neither                  : {ct['neither']:>4} ({ct['neither']/tot:.0%})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="cosmos_idmt.json (GT reconstructed from sibling themes file)")
    parser.add_argument("--min-gt", type=int, default=1, help="only tickets with >= this many GT VS")
    parser.add_argument("--sample", type=int, default=0, help="evaluate only N tickets (default: all)")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--judge", action="store_true",
                        help="add the LLM content-relevance diagnostic (1 batched call per ticket): "
                             "is each retrieved ticket TOPICALLY similar, not just label-matched")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--out", default="out/eval/retrieval_eval.json")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
