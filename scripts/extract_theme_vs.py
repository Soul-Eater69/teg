"""Standalone extraction test: ticket -> linked themes -> Value Stream (id + name).

Different from the production ingestion path on purpose:
  - accepts ANY issue-link type (not only implement-links): a "theme" may be linked any way.
  - reads the Value Stream DIRECTLY from the linked issue's "Business Value Stream" field,
    formatted "<vs name> {<vs id>}" (e.g. "Configure Price {VS1024}") - no fuzzy match, no
    catalogue verification, no LLM, no summary, no embedding.

For each ticket it fetches the issue's links, fetches each linked issue, reads the Business
Value Stream field, and parses out (valueStreamName, valueStreamId). It also reports the link
KINDS seen (link type + direction + linked issue type) so you can see what link shapes exist.

The Business Value Stream custom-field id is discovered by name from /rest/api/2/field, so you
don't need to hard-code customfield_#####; override with --field-name or --field-id.

Usage (needs Jira creds in .env):
  uv run python scripts/extract_theme_vs.py tickets.txt --out out/extract/theme_vs.json
  uv run python scripts/extract_theme_vs.py IDMT-19761 IDMT-20000       # ids inline
  uv run python scripts/extract_theme_vs.py tickets.txt --field-id customfield_12345
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from teg.config.settings import load_settings
from teg.ingestion.extraction.value_stream_field import parse_value_stream

_DEFAULT_FIELD_NAME = "Business Value Stream"


def _read_ids(arg: str) -> list[str]:
    """A path to a file (one id per line) or a single inline id."""
    path = Path(arg)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        return [s.strip() for s in lines if s.strip() and not s.strip().startswith("#")]
    return [arg.strip()]


def _link_targets(issuelinks: list) -> list[dict]:
    """Flatten issuelinks into {key, linkType, direction, issueType} for each linked issue."""
    out: list[dict] = []
    for link in issuelinks or []:
        link_type = link.get("type") or {}
        inward, outward = link.get("inwardIssue"), link.get("outwardIssue")
        issue = inward or outward
        if not isinstance(issue, dict):
            continue
        direction = "inward" if inward else "outward"
        label = link_type.get("inward") if inward else link_type.get("outward")
        out.append({
            "key": str(issue.get("key") or ""),
            "linkType": str(link_type.get("name") or ""),
            "linkLabel": str(label or ""),
            "direction": direction,
            "issueType": str(((issue.get("fields") or {}).get("issuetype") or {}).get("name") or ""),
        })
    return out


async def _discover_field_id(http: httpx.AsyncClient, api: str, field_name: str) -> str | None:
    resp = await http.get(f"/rest/api/{api}/field")
    resp.raise_for_status()
    wanted = field_name.strip().lower()
    for field in resp.json() or []:
        if str(field.get("name") or "").strip().lower() == wanted:
            return str(field.get("id") or "")
    return None


async def _get_issue(http: httpx.AsyncClient, api: str, key: str, fields: str) -> dict:
    resp = await http.get(f"/rest/api/{api}/issue/{key}", params={"fields": fields})
    resp.raise_for_status()
    return resp.json() or {}


async def extract_ticket(http, api, ticket_id, bvs_field, sem) -> dict:
    async with sem:
        try:
            issue = await _get_issue(http, api, ticket_id, "summary,issuetype,issuelinks")
        except Exception as exc:
            return {"ticketId": ticket_id, "error": f"{type(exc).__name__}: {exc}", "themes": []}
        fields = issue.get("fields") or {}
        targets = _link_targets(fields.get("issuelinks") or [])

        async def _theme(t: dict) -> dict:
            try:
                linked = await _get_issue(http, api, t["key"], f"summary,issuetype,{bvs_field}")
            except Exception as exc:
                return {**t, "valueStreamName": None, "valueStreamId": None,
                        "error": f"{type(exc).__name__}: {exc}"}
            lf = linked.get("fields") or {}
            vs = parse_value_stream(lf.get(bvs_field))
            return {
                "themeStableId": str(linked.get("id") or ""),  # 7-digit internal Jira id
                "key": t["key"], "summary": str(lf.get("summary") or ""),
                "linkType": t["linkType"], "linkLabel": t["linkLabel"],
                "direction": t["direction"], "issueType": t["issueType"],
                "valueStreamName": vs[0] if vs else None,
                "valueStreamId": vs[1] if vs else None,
                "rawBvs": lf.get(bvs_field),
            }

        ticket_stable_id = str(issue.get("id") or "")  # 7-digit internal Jira id of the ER
        themes = await asyncio.gather(*(_theme(t) for t in targets)) if targets else []
        with_vs = sum(1 for th in themes if th.get("valueStreamId"))
        print(f"{ticket_id} (id={ticket_stable_id}): {len(themes)} links, {with_vs} with a Value Stream")
        for th in themes:
            if th.get("valueStreamId"):
                print(f"    theme {th['key']} (id={th['themeStableId']}) -> "
                      f"{th['valueStreamName']} {{{th['valueStreamId']}}}")
        return {
            "ticketId": ticket_id, "ticketStableId": ticket_stable_id,
            "title": str(fields.get("summary") or ""),
            "issueType": str((fields.get("issuetype") or {}).get("name") or ""),
            "themes": themes,
        }


async def main(args) -> None:
    ids: list[str] = []
    for a in args.tickets:
        ids.extend(_read_ids(a))
    settings = load_settings()
    api = settings.jira_api_version
    http = httpx.AsyncClient(
        base_url=settings.jira_base_url,
        headers={"Authorization": f"Bearer {settings.jira_token}"},
        timeout=settings.jira_timeout_seconds,
        verify=settings.jira_verify_ssl,
    )
    try:
        bvs_field = args.field_id or await _discover_field_id(http, api, args.field_name)
        if not bvs_field:
            raise SystemExit(
                f"could not find the '{args.field_name}' field on this Jira; "
                "pass --field-id customfield_##### explicitly"
            )
        print(f"Business Value Stream field id: {bvs_field}")
        print(f"extracting {len(ids)} tickets (concurrency={args.concurrency})\n")
        sem = asyncio.Semaphore(args.concurrency)
        results = await asyncio.gather(*(extract_ticket(http, api, t, bvs_field, sem) for t in ids))
    finally:
        await http.aclose()

    # Summary: link kinds + VS extraction coverage.
    link_kinds: dict[str, int] = {}
    total_links = total_vs = tickets_with_vs = 0
    for r in results:
        if r.get("themes"):
            tickets_with_vs += any(th.get("valueStreamId") for th in r["themes"])
        for th in r.get("themes", []):
            kind = f"{th['linkType']} ({th['direction']}) -> {th['issueType']}"
            link_kinds[kind] = link_kinds.get(kind, 0) + 1
            total_links += 1
            total_vs += 1 if th.get("valueStreamId") else 0

    print("\n" + "=" * 60)
    print(f"tickets: {len(results)}  |  links: {total_links}  |  links with VS: {total_vs}  "
          f"|  tickets with >=1 VS: {tickets_with_vs}")
    print("\nlink kinds (type, direction, linked issue type):")
    for kind, n in sorted(link_kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4}  {kind}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tickets", nargs="+", help="tickets file(s) and/or inline IDMT ids")
    parser.add_argument("--field-name", default=_DEFAULT_FIELD_NAME, help="VS field display name")
    parser.add_argument("--field-id", default="", help="explicit customfield_##### (skips discovery)")
    parser.add_argument("--out", default="out/extract/theme_vs.json")
    parser.add_argument("--concurrency", type=int, default=6)
    asyncio.run(main(parser.parse_args()))
