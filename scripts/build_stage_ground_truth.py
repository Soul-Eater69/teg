"""Build stage ground truth from linked Jira Themes and their Epics.

For each IDMT ticket: ticket -> linked Themes (Value Streams) -> child Epics (stages),
canonicalized against the stage catalogue, plus each Theme's description / Business Needs
and each Epic's L2 / L3 capability fields. This is the answer key for stage-selection and
theme-package evaluation.

Usage (needs Jira creds in .env):
  uv run python scripts/build_stage_ground_truth.py tickets.txt
  uv run python scripts/build_stage_ground_truth.py IDMT-19761 IDMT-20000        # ids inline
  uv run python scripts/build_stage_ground_truth.py tickets.txt --l2-field customfield_18602
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

import httpx

from teg.config.settings import load_settings
from teg.ingestion.catalogues.loader import load_value_stream_catalogue
from teg.ingestion.ground_truth.stage_ground_truth import (
    StageGtFields,
    TicketStageGroundTruth,
    build_ticket_stage_ground_truth,
)


class HttpxJiraClient:
    """StageJiraClient over Jira REST (get issue + JQL search)."""

    def __init__(self, http: httpx.AsyncClient, *, api: str) -> None:
        self._http = http
        self._api = api

    async def get_issue(self, key: str, *, fields: Sequence[str]) -> dict:
        resp = await self._http.get(
            f"/rest/api/{self._api}/issue/{key}", params={"fields": ",".join(fields)}
        )
        resp.raise_for_status()
        return resp.json() or {}

    async def search(self, jql: str, *, fields: Sequence[str]) -> list[dict]:
        resp = await self._http.get(
            f"/rest/api/{self._api}/search",
            params={"jql": jql, "maxResults": "100", "fields": ",".join(fields)},
        )
        resp.raise_for_status()
        return list((resp.json() or {}).get("issues") or [])

    async def discover_field_id(self, field_name: str) -> str:
        resp = await self._http.get(f"/rest/api/{self._api}/field")
        resp.raise_for_status()
        wanted = field_name.strip().lower()
        for field in resp.json() or []:
            if str(field.get("name") or "").strip().lower() == wanted:
                return str(field.get("id") or "")
        return ""


def _read_ids(arg: str) -> list[str]:
    path = Path(arg)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        return [s.strip() for s in lines if s.strip() and not s.strip().startswith("#")]
    return [arg.strip()]


def _to_dict(ticket: TicketStageGroundTruth) -> dict:
    return asdict(ticket)


def _summarize(ticket: TicketStageGroundTruth) -> str:
    stage_count = sum(len(t.stages) for t in ticket.themes)
    resolved = sum(1 for t in ticket.themes for s in t.stages if s.stage_id)
    return (f"{ticket.ticket_id}: {len(ticket.themes)} themes, "
            f"{resolved}/{stage_count} stages resolved")


async def main(args: argparse.Namespace) -> None:
    ids: list[str] = []
    for a in args.tickets:
        ids.extend(_read_ids(a))
    if not ids:
        raise SystemExit("no ticket ids given")

    settings = load_settings()
    catalogue = load_value_stream_catalogue(args.catalogue)
    defaults = StageGtFields()

    http = httpx.AsyncClient(
        base_url=settings.jira_base_url,
        headers={"Authorization": f"Bearer {settings.jira_token}"},
        timeout=settings.jira_timeout_seconds,
        verify=settings.jira_verify_ssl,
    )
    try:
        jira = HttpxJiraClient(http, api=settings.jira_api_version)

        async def _resolve(explicit: str, display_name: str, fallback: str) -> str:
            # explicit flag wins; else discover by display name (ids drift between Jira instances);
            # else the hardcoded default.
            if explicit:
                return explicit
            return await jira.discover_field_id(display_name) or fallback

        vs_field = settings.jira_value_stream_field or await jira.discover_field_id(
            settings.jira_value_stream_field_name
        )
        if not vs_field:
            raise SystemExit(
                f"could not resolve the '{settings.jira_value_stream_field_name}' field id; "
                "set jira_value_stream_field in .env"
            )
        fields = StageGtFields(
            stage=await _resolve(args.stage_field, "Value Stream Stage", defaults.stage),
            business_needs=await _resolve(args.business_needs_field, "Business Needs", defaults.business_needs),
            l2_capability=await _resolve(args.l2_field, "L2 Business Capability Model", defaults.l2_capability),
            l3_capability=await _resolve(args.l3_field, "L3 Business Capability Model", defaults.l3_capability),
        )
        print(f"Business Value Stream field: {vs_field}")
        print(f"stage field (Epic): {fields.stage}  | L2={fields.l2_capability} "
              f"L3={fields.l3_capability} | business needs={fields.business_needs}")
        print(f"building stage GT for {len(ids)} tickets (concurrency={args.concurrency})\n")

        sem = asyncio.Semaphore(args.concurrency)

        async def _one(ticket_id: str) -> TicketStageGroundTruth:
            async with sem:
                try:
                    gt = await build_ticket_stage_ground_truth(
                        ticket_id, jira=jira, catalogue=catalogue,
                        value_stream_field=vs_field, fields=fields,
                    )
                except Exception as exc:  # one bad ticket must not stop the batch
                    print(f"  ERROR {ticket_id}: {type(exc).__name__}: {exc}")
                    return TicketStageGroundTruth(
                        ticket_id=ticket_id, summary="", description="",
                        warnings=[f"{type(exc).__name__}: {exc}"],
                    )
                print(f"  {_summarize(gt)}")
                return gt

        tickets = await asyncio.gather(*(_one(t) for t in ids))
    finally:
        await http.aclose()

    # Field health: flag a field that never populated (likely the wrong id).
    all_stages = [s for t in tickets for th in t.themes for s in th.stages]
    by_method: dict[str, int] = {}
    for s in all_stages:
        by_method[s.match_method] = by_method.get(s.match_method, 0) + 1
    print(f"\n  stage match methods: {by_method}")
    if all_stages and not by_method.get("field"):
        print(f"  NOTE: the Value Stream Stage field {fields.stage} resolved 0 stages - likely the "
              "wrong id. Run: inspect_jira_fields.py <an-epic-key> --grep stream  and pass --stage-field")
    l2_seen = any(th.l2_capabilities for t in tickets for th in t.themes)
    l3_seen = any(th.l3_capabilities for t in tickets for th in t.themes)
    if not l2_seen:
        print(f"  NOTE: L2 field {fields.l2_capability} was empty for every Theme "
              "- verify the id with --l2-field")
    if not l3_seen:
        print(f"  NOTE: L3 field {fields.l3_capability} was empty for every Theme "
              "- verify the id with --l3-field")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": "jira", "tickets": [_to_dict(t) for t in tickets]}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    jsonl = out.with_suffix(".jsonl")
    with jsonl.open("w", encoding="utf-8") as fh:
        for t in tickets:
            fh.write(json.dumps(_to_dict(t), ensure_ascii=False) + "\n")

    total_stages = sum(len(th.stages) for t in tickets for th in t.themes)
    resolved = sum(1 for t in tickets for th in t.themes for s in th.stages if s.stage_id)
    print(f"\ntickets: {len(tickets)} | stages: {resolved}/{total_stages} resolved")
    print(f"-> {out}\n-> {jsonl}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build stage ground truth from Jira Themes/Epics.")
    p.add_argument("tickets", nargs="+", help="tickets file(s) and/or inline IDMT ids")
    p.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    p.add_argument("--out", default="out/stage_eval/stage_ground_truth.json")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--business-needs-field", default="", help="override Business Needs customfield")
    p.add_argument("--l2-field", default="", help="override Epic L2 capability customfield")
    p.add_argument("--l3-field", default="", help="override Epic L3 capability customfield")
    p.add_argument("--stage-field", default="", help="override Epic Value Stream Stage customfield")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args()))
