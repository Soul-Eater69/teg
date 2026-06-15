"""Measure generation latency + token usage for ALL theme-generation components in one run.

Runs each generator on the same sample of tickets (raw idea-card text + GT value streams / stages,
no retrieval, no judges) and prints one consolidated table: per-component avg latency and avg tokens
(prompt / completion / total). Each component uses its OWN LLM client so token counts are isolated.

Components: stage selection (one_call), L3 capability (one_call), theme description (body+framing),
business needs (per VS). Value-stream selection involves retrieval and is measured by eval_vs.

Usage (needs the LLM gateway):
  uv run python scripts/measure_costs.py out/idmt/cosmos_idmt.json --sample 15
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from teg.config.settings import load_settings
from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.integrations.llm import build_llm_client
from teg.theme.business_needs import generate_business_needs
from teg.theme.capabilities import generate_capabilities_traced
from teg.theme.description import (
    assemble_description,
    generate_description_body,
    generate_vs_framings,
)
from teg.theme.stage_catalogue import StageCatalogue
from teg.theme.stage_selection import StageSelectionInput, select_stages_for_all_traced

_RAW_BUDGET = 96_000


def _load_condensed(path: str) -> dict[str, dict]:
    docs = json.loads(Path(path).read_text(encoding="utf-8"))
    return {d.get("key", ""): (d.get("properties") or {}) for d in docs if d.get("key")}


def _load_gt(path: str) -> dict[str, dict[str, dict]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict[str, dict]] = {}
    for ticket in payload.get("tickets") or []:
        by_vs: dict[str, dict] = {}
        for theme in ticket.get("themes") or []:
            vs_id = theme.get("value_stream_id") or ""
            stages = {s.get("stage_id") for s in theme.get("stages") or [] if s.get("stage_id")}
            if vs_id and stages:
                e = by_vs.setdefault(vs_id, {"name": theme.get("value_stream_name") or "", "stages": set()})
                e["stages"] |= stages
        if by_vs:
            out[ticket.get("ticket_id") or ""] = by_vs
    return out


def _ctx(props: dict) -> CondensedContext:
    return CondensedContext(
        summary_fields=SummaryFields(generated_summary=str(props.get("rawText") or "")[:_RAW_BUDGET],
                                     business_problem="", business_capability=""),
        generation_signals=GenerationSignals())


def _stages(catalogue, vs_id, gt_stages):
    return [s for s in catalogue.stages_for(vs_id) if s.stage_id in gt_stages]


async def main(args: argparse.Namespace) -> None:
    settings = load_settings()
    condensed = _load_condensed(args.condensed)
    gt = _load_gt(args.gt)
    catalogue = StageCatalogue.from_catalogue(load_value_stream_catalogue(args.catalogue))

    tickets = [t for t in gt if t in condensed]
    if args.sample and args.sample < len(tickets):
        import random
        tickets = sorted(random.Random(args.seed).sample(tickets, args.sample))
    elif args.count:
        tickets = tickets[:args.count]
    if not tickets:
        raise SystemExit("no tickets to measure")
    print(f"measuring {len(tickets)} tickets (raw text only)\n")
    sem = asyncio.Semaphore(args.concurrency)

    # One client per component -> isolated token counts. (component, unit, latencies, client)
    clients = {name: build_llm_client(settings) for name in
               ("stages", "l3", "description", "business_needs")}
    lat: dict[str, list[float]] = {k: [] for k in clients}

    async def _ticket(tid: str) -> None:
        async with sem:
            props = condensed[tid]
            ctx = _ctx(props)
            vs_list = list(gt[tid].items())
            approved = [ApprovedValueStream(value_stream_id=v, value_stream_name=e["name"])
                        for v, e in vs_list]
            inputs = [StageSelectionInput(
                value_stream=ApprovedValueStream(value_stream_id=v, value_stream_name=e["name"]),
                value_stream_description=catalogue.description_for(v),
                value_proposition=catalogue.value_proposition_for(v),
                stages=catalogue.stages_for(v)) for v, e in vs_list if catalogue.stages_for(v)]

            # Stages (one_call, per ticket)
            if inputs:
                t = perf_counter()
                await select_stages_for_all_traced(condensed=ctx, inputs=inputs, llm_client=clients["stages"])
                lat["stages"].append(perf_counter() - t)

            # Description (body + batched framing, per ticket)
            t = perf_counter()
            await asyncio.gather(
                generate_description_body(condensed=ctx, llm_client=clients["description"]),
                generate_vs_framings(condensed=ctx, approved_value_streams=approved,
                                     value_stream_details={v: (catalogue.description_for(v),
                                                               catalogue.value_proposition_for(v))
                                                           for v, _ in vs_list},
                                     llm_client=clients["description"]))
            lat["description"].append(perf_counter() - t)

            # L3 + business needs (per VS)
            for v, e in vs_list:
                stages = _stages(catalogue, v, e["stages"])
                vs = ApprovedValueStream(value_stream_id=v, value_stream_name=e["name"])
                if any(s.capabilities for s in stages):
                    t = perf_counter()
                    await generate_capabilities_traced(
                        condensed=ctx, value_stream=vs, value_stream_description=catalogue.description_for(v),
                        selected_stages=stages, llm_client=clients["l3"])
                    lat["l3"].append(perf_counter() - t)
                if stages:
                    t = perf_counter()
                    await generate_business_needs(
                        condensed=ctx, value_stream=vs, value_stream_description=catalogue.description_for(v),
                        value_proposition=catalogue.value_proposition_for(v),
                        selected_stages=stages, llm_client=clients["business_needs"])
                    lat["business_needs"].append(perf_counter() - t)
        print(f"  {tid} done")

    await asyncio.gather(*(_ticket(t) for t in tickets))

    units = {"stages": "ticket", "description": "ticket", "l3": "VS", "business_needs": "VS"}
    print(f"\n{'='*78}\nGENERATION COST  ({len(tickets)} tickets, raw text only)\n{'='*78}")
    print(f"{'component':16} {'unit':7} {'n':>4} {'avg lat':>8} {'med lat':>8} {'max lat':>8}  "
          f"{'avg tok':>8} {'in':>7} {'out':>7}")
    for name, client in clients.items():
        ls = sorted(lat[name]); u = client.usage
        if not ls:
            continue
        print(f"{name:16} {units[name]:7} {len(ls):>4} {sum(ls)/len(ls):>7.1f}s "
              f"{ls[len(ls)//2]:>7.1f}s {ls[-1]:>7.1f}s  "
              f"{u['avg_total']:>8.0f} {u['avg_prompt']:>7.0f} {u['avg_completion']:>7.0f}")
    print(f"\nnote: latency unit is per {{ticket | VS}}; tokens are per LLM call. "
          f"Value-stream selection (retrieval + select) is measured by eval_vs.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Measure generation latency + tokens for all components.")
    p.add_argument("condensed")
    p.add_argument("--gt", default="out/stage_eval/stage_ground_truth.json")
    p.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    p.add_argument("--sample", type=int, default=0)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=3)
    asyncio.run(main(p.parse_args()))
