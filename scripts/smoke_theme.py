"""Manual smoke test for Theme generation (Contract C) against the live LLM.

Generates one theme package per approved Value Stream. Approved VS ids are resolved to
names from the catalogue map (their stages/capabilities are read from it too).

Prerequisites:
  1. cp .env.example .env  and fill in LLM/IDP values
  2. uv sync --extra dev
  3. uv run python scripts/smoke_theme.py "<ticket title>" "<summary text>" VSR00074583 VSR00074584 \
        --catalogue data/value_stream_capability_map.json
"""

from __future__ import annotations

import argparse
import asyncio
from time import perf_counter

from teg.bootstrap import build_theme_service
from teg.contracts.theme_io import (
    ApprovedValueStream,
    CondensedContext,
    ThemeGenerationRequest,
)
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.loader import load_value_stream_catalogue


async def main(title: str, summary: str, vs_ids: list[str], catalogue_path: str) -> None:
    names = {vs.value_stream_id: vs.value_stream_name for vs in load_value_stream_catalogue(catalogue_path)}
    approved = [ApprovedValueStream(value_stream_id=i, value_stream_name=names.get(i, i)) for i in vs_ids]

    service = build_theme_service(catalogue_path=catalogue_path)
    request = ThemeGenerationRequest(
        ticket_id="SMOKE",
        ticket_title=title,
        condensed=CondensedContext(
            summary_fields=SummaryFields(
                generated_summary=summary, business_problem="", business_capability=""
            ),
            generation_signals=GenerationSignals(),
        ),
        approved_value_streams=approved,
    )

    start = perf_counter()
    response = await service.generate(request)
    print(f"# {len(response.theme_packages)} theme packages in {perf_counter() - start:.2f}s\n")

    for pkg in response.theme_packages:
        print("=" * 88)
        print(f"THEME: {pkg.theme_title}  ({pkg.value_stream_id})\n")
        print("--- description ---\n" + pkg.theme_description + "\n")
        print("--- selected stages ---")
        for s in pkg.selected_stages:
            print(f"  {s.stage_id}  {s.stage_name} - {s.reason}")
        print("\n--- business needs ---\n" + (pkg.business_needs or "(none)") + "\n")
        print("--- L3 capabilities ---")
        for sc in pkg.l3_capabilities:
            for c in sc.capabilities:
                print(f"  [{sc.stage_name}] {c.capability_id}  {c.name} - {c.reason}")
        print("--- L2 capabilities (derived) ---")
        for sc in pkg.l2_capabilities:
            for c in sc.capabilities:
                print(f"  [{sc.stage_name}] {c.capability_id}  {c.name}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("title")
    parser.add_argument("summary")
    parser.add_argument("vs_ids", nargs="+", help="approved Value Stream ids (VSR...)")
    parser.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    args = parser.parse_args()
    asyncio.run(main(args.title, args.summary, args.vs_ids, args.catalogue))
