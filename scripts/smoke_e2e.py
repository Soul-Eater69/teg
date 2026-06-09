"""End-to-end smoke: ticket -> condense -> VS prediction -> theme generation.

Runs the whole runtime path with no manual VS ids: condense the ticket, predict the top-N
value streams, treat those as the SME-approved set, then generate theme content for each.

Modes (--only): core (description+stages, default) | description | stages | needs | caps | all

Usage:
  uv run python -m scripts.smoke_e2e --ticket IDMT-19761 --count 5
  uv run python -m scripts.smoke_e2e --ticket IDMT-19761 --count 5 --only all
  uv run python -m scripts.smoke_e2e --summary "..." --title "T" --count 3 --only stages
"""

from __future__ import annotations

import argparse
import asyncio
from time import perf_counter

from teg.bootstrap import build_condense_service, build_value_stream_service
from teg.config.settings import load_settings
from teg.contracts.condense_io import CondenseRequest
from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.contracts.value_stream_io import ValueStreamRequest
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.integrations.llm import build_llm_client
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.theme.business_needs import generate_business_needs
from teg.theme.capabilities import generate_capabilities
from teg.theme.description import generate_theme_description
from teg.theme.stage_catalogue import StageCatalogue
from teg.theme.stage_selection import select_stages


async def main(args) -> None:
    catalogue = StageCatalogue.from_catalogue(load_value_stream_catalogue(args.catalogue))
    llm = build_llm_client(load_settings())

    # 1. condense
    if args.ticket:
        print(f"# condensing {args.ticket} ...")
        t0 = perf_counter()
        c = (await build_condense_service().condense(CondenseRequest(ticket_id=args.ticket))).condensed
        summary_fields = c.summary_fields
        condensed = CondensedContext(summary_fields=c.summary_fields, generation_signals=c.generation_signals)
        title = args.title or c.ticket_title
        print(f"# condensed in {perf_counter()-t0:.2f}s  |  {summary_fields.generated_summary[:110]}")
    else:
        summary_fields = SummaryFields(generated_summary=args.summary, business_problem="", business_capability="")
        condensed = CondensedContext(summary_fields=summary_fields, generation_signals=GenerationSignals())
        title = args.title or "SMOKE"

    # 2. VS prediction -> top N (the "approved" set)
    t0 = perf_counter()
    vs_resp = await build_value_stream_service().predict(
        ValueStreamRequest(ticket_id="SMOKE", summary_fields=summary_fields, requested_count=args.count)
    )
    print(f"\n# {len(vs_resp.recommendations)} value streams predicted in {perf_counter()-t0:.2f}s (treated as approved):")
    for r in vs_resp.recommendations:
        print(f"  {r.confidence:5.1f}  {r.support_type:8} {r.value_stream_name}  ({r.value_stream_id})")
    approved = [ApprovedValueStream(value_stream_id=r.value_stream_id, value_stream_name=r.value_stream_name)
                for r in vs_resp.recommendations]

    # 3. theme generation per approved VS
    for vs in approved:
        desc = catalogue.description_for(vs.value_stream_id)
        prop = catalogue.value_proposition_for(vs.value_stream_id)
        stages = catalogue.stages_for(vs.value_stream_id)
        print("\n" + "=" * 88)
        print(f"VS: {vs.value_stream_name}  ({vs.value_stream_id})  | {len(stages)} governed stages")
        print(f"THEME TITLE: {title} - {vs.value_stream_name}\n")

        selected = None
        if args.only in ("description", "core", "all"):
            t0 = perf_counter()
            text = await generate_theme_description(condensed=condensed, value_stream_id=vs.value_stream_id,
                value_stream_name=vs.value_stream_name, value_stream_description=desc, value_proposition=prop, llm_client=llm)
            print(f"--- DESCRIPTION [{perf_counter()-t0:.2f}s] ---\n{text}\n")

        if args.only in ("stages", "core", "needs", "caps", "all"):
            t0 = perf_counter()
            selected = await select_stages(condensed=condensed, value_stream=vs,
                value_stream_description=desc, value_proposition=prop, stages=stages, llm_client=llm)
            print(f"--- SELECTED STAGES [{perf_counter()-t0:.2f}s] ---")
            for s in selected:
                print(f"  {s.stage_id}  {s.stage_name} - {s.reason}")
            if not selected:
                print("  (none / broad_or_unclear)")
            print()

        by_id = {s.stage_id: s for s in stages}
        sel_stages = [by_id[s.stage_id] for s in (selected or []) if s.stage_id in by_id]

        if args.only in ("needs", "all") and sel_stages:
            t0 = perf_counter()
            needs = await generate_business_needs(condensed=condensed, value_stream=vs,
                value_stream_description=desc, value_proposition=prop, selected_stages=sel_stages, llm_client=llm)
            print(f"--- BUSINESS NEEDS [{perf_counter()-t0:.2f}s] ---\n{needs or '(none)'}\n")

        if args.only in ("caps", "all") and sel_stages:
            t0 = perf_counter()
            l3, l2 = await generate_capabilities(condensed=condensed, value_stream=vs,
                value_stream_description=desc, selected_stages=sel_stages, llm_client=llm)
            print(f"--- L3 CAPABILITIES [{perf_counter()-t0:.2f}s] ---")
            for sc in l3:
                for cap in sc.capabilities:
                    print(f"  [{sc.stage_name}] {cap.capability_id}  {cap.name} - {cap.reason}")
            print("--- L2 (derived 1-1) ---")
            for sc in l2:
                for cap in sc.capabilities:
                    print(f"  [{sc.stage_name}] {cap.capability_id}  {cap.name}")
            print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticket", help="IDMT ticket id; condense it first")
    parser.add_argument("--summary", help="raw summary text (when not using --ticket)")
    parser.add_argument("--title", help="ticket title")
    parser.add_argument("--count", type=int, default=5, help="number of value streams to predict + theme")
    parser.add_argument("--only", choices=["core", "description", "stages", "needs", "caps", "all"], default="core")
    parser.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    args = parser.parse_args()
    if not args.ticket and not args.summary:
        raise SystemExit("provide --ticket IDMT-#### or --summary \"...\"")
    asyncio.run(main(args))
