"""Manual smoke test for Theme generation (Contract C) against the live LLM.

Test each generator separately or the whole package. Approved VS ids resolve to names +
governed stages/capabilities from the catalogue map.

Modes:
  --only description   just the theme description text
  --only stages        just stage selection
  --only needs         business needs (runs stage selection first to get the stages)
  --only caps          L3 prediction + derived L2 (runs stage selection first)
  --only all           the full ThemePackage (default)

Context:
  --ticket IDMT-19761  condense the ticket first (real path), OR
  --summary "..."  --title "..."   raw text

Usage:
  uv run python -m scripts.smoke_theme --ticket IDMT-19761 VSR00074590 --only description
  uv run python -m scripts.smoke_theme --summary "..." --title "T" VSR00074590 --only stages
"""

from __future__ import annotations

import argparse
import asyncio
from time import perf_counter

from teg.bootstrap import build_condense_service
from teg.contracts.condense_io import CondenseRequest
from teg.contracts.theme_io import ApprovedValueStream, CondensedContext
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.integrations.llm import build_llm_client
from teg.config.settings import load_settings
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.theme.business_needs import generate_business_needs
from teg.theme.capabilities import generate_capabilities
from teg.theme.description import (
    assemble_description,
    generate_description_body,
    generate_vs_framings,
)
from teg.theme.stage_catalogue import StageCatalogue
from teg.theme.stage_selection import select_stages


async def _condensed_context(ticket: str | None, summary: str | None) -> tuple[CondensedContext, str]:
    if ticket:
        print(f"# condensing {ticket} ...")
        t0 = perf_counter()
        c = (await build_condense_service().condense(CondenseRequest(ticket_id=ticket))).condensed
        print(f"# condensed in {perf_counter() - t0:.2f}s")
        return CondensedContext(summary_fields=c.summary_fields, generation_signals=c.generation_signals), c.ticket_title
    sf = SummaryFields(generated_summary=summary or "", business_problem="", business_capability="")
    return CondensedContext(summary_fields=sf, generation_signals=GenerationSignals()), "SMOKE"


def _timed(label):
    def deco(coro):
        async def wrap(*a, **k):
            t0 = perf_counter()
            r = await coro(*a, **k)
            print(f"[{label}: {perf_counter() - t0:.2f}s]")
            return r
        return wrap
    return deco


async def main(args) -> None:
    catalogue = StageCatalogue.from_catalogue(load_value_stream_catalogue(args.catalogue))
    names = {vs.value_stream_id: vs.value_stream_name for vs in load_value_stream_catalogue(args.catalogue)}
    llm = build_llm_client(load_settings())
    condensed, title = await _condensed_context(args.ticket, args.summary)
    if args.title:
        title = args.title

    for vs_id in args.vs_ids:
        vs = ApprovedValueStream(value_stream_id=vs_id, value_stream_name=names.get(vs_id, vs_id))
        desc = catalogue.description_for(vs_id)
        prop = catalogue.value_proposition_for(vs_id)
        stages = catalogue.stages_for(vs_id)
        print("\n" + "=" * 88)
        print(f"VS: {vs.value_stream_name}  ({vs_id})  | {len(stages)} governed stages")
        print(f"THEME TITLE: {title} - {vs.value_stream_name}\n")

        selected = None
        if args.only in ("description", "all"):
            t0 = perf_counter()
            body = await generate_description_body(condensed=condensed, llm_client=llm)
            framings = await generate_vs_framings(condensed=condensed, approved_value_streams=[vs],
                value_stream_details={vs_id: (desc, prop)}, llm_client=llm)
            text = assemble_description(framings.get(vs_id, ""), body)
            print(f"--- DESCRIPTION [{perf_counter()-t0:.2f}s] ---\n{text}\n")

        if args.only in ("stages", "needs", "caps", "all"):
            t0 = perf_counter()
            selected = await select_stages(condensed=condensed, value_stream=vs,
                value_stream_description=desc, value_proposition=prop, stages=stages, llm_client=llm)
            print(f"--- SELECTED STAGES [{perf_counter()-t0:.2f}s] ---")
            for s in selected:
                print(f"  {s.stage_id}  {s.stage_name} - {s.reason}")
            if not selected:
                print("  (none / broad_or_unclear)")
            print()

        if args.only in ("needs", "all") and selected:
            by_id = {s.stage_id: s for s in stages}
            sel_stages = [by_id[s.stage_id] for s in selected if s.stage_id in by_id]
            t0 = perf_counter()
            needs = await generate_business_needs(condensed=condensed, value_stream=vs,
                value_stream_description=desc, value_proposition=prop, selected_stages=sel_stages, llm_client=llm)
            print(f"--- BUSINESS NEEDS [{perf_counter()-t0:.2f}s] ---\n{needs or '(none)'}\n")

        if args.only in ("caps", "all") and selected:
            by_id = {s.stage_id: s for s in stages}
            sel_stages = [by_id[s.stage_id] for s in selected if s.stage_id in by_id]
            t0 = perf_counter()
            l3, l2 = await generate_capabilities(condensed=condensed, value_stream=vs,
                value_stream_description=desc, selected_stages=sel_stages, llm_client=llm)
            print(f"--- L3 CAPABILITIES [{perf_counter()-t0:.2f}s] ---")
            for sc in l3:
                for c in sc.capabilities:
                    print(f"  [{sc.stage_name}] {c.capability_id}  {c.name} - {c.reason}")
            print("--- L2 (derived 1-1) ---")
            for sc in l2:
                for c in sc.capabilities:
                    print(f"  [{sc.stage_name}] {c.capability_id}  {c.name}")
            print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("vs_ids", nargs="+", help="approved Value Stream ids (VSR...)")
    parser.add_argument("--ticket", help="IDMT ticket id; condense it first")
    parser.add_argument("--summary", help="raw summary text (when not using --ticket)")
    parser.add_argument("--title", help="ticket title (raw mode)")
    parser.add_argument("--only", choices=["description", "stages", "needs", "caps", "all"], default="all")
    parser.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    args = parser.parse_args()
    if not args.ticket and not args.summary:
        raise SystemExit("provide --ticket IDMT-#### or --summary \"...\"")
    asyncio.run(main(args))
