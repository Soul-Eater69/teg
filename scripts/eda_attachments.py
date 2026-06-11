"""Phase 1 EDA — attachments across the historical IDMT tickets.

Collects per-attachment metadata + extracted text (live Jira), then computes the attachment
profile that drives condense/ingestion sizing decisions: attachments per ticket, file types,
sizes, extracted character counts, description length, and how many tickets exceed a token
budget when their attachment text is combined.

Reuses the production clients so the numbers match what ingestion actually sees:
  build_jira_client(settings).fetch_ticket / download_attachment  +  build_attachment_extractor().

Usage (on a box with Jira + IDP creds; install: uv sync --extra eda --extra extract):
  uv run python scripts/eda_attachments.py tickets.txt --out out/eda/attachments --docx
  # collection is cached to <out>/attachments_raw.json; re-run analysis without re-fetching:
  uv run python scripts/eda_attachments.py tickets.txt --out out/eda/attachments --use-cache --docx

The notebook notebooks/attachments_eda.ipynb imports these functions for an interactive view.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from teg.condense.attachment_ranker import is_idea_card, is_supported, select_attachments
from teg.config.settings import load_settings
from teg.integrations.files import build_attachment_extractor
from teg.integrations.jira import build_jira_client

TOKEN_BUDGET = 20_000  # condense's working context budget; we flag tickets above it


# ---------------------------------------------------------------- collection

def load_ticket_ids(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [s.strip() for s in lines if s.strip() and not s.strip().startswith("#")]


def _ext(filename: str) -> str:
    name = filename.lower().strip()
    return name.rsplit(".", 1)[-1] if "." in name else "(none)"


def estimate_tokens(text: str) -> int:
    """Token count via tiktoken when available, else a ~4-chars-per-token estimate."""
    if not text:
        return 0
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 4)


async def collect(
    ticket_ids: list[str],
    *,
    concurrency: int = 4,
    ticket_timeout: float = 90.0,
    done_records: list[dict] | None = None,
    checkpoint_path: Path | None = None,
    checkpoint_every: int = 10,
) -> list[dict]:
    """One record per (ticket, attachment), plus a synthetic 'description' pseudo-attachment.

    Each record: ticketId, kind (attachment|description), filename, ext, mimeType, sizeBytes,
    charCount, tokenEst, supported, ideaCard, extractError. Failures are recorded, not fatal.

    Robust to stalls: every fetch/download/extract is bounded by ``ticket_timeout`` (a slow
    attachment can't hang a worker slot). Resumable: pass ``done_records`` to skip already-collected
    tickets, and ``checkpoint_path`` to flush progress every ``checkpoint_every`` tickets - so a
    crash/stop loses at most that many, and re-running continues from where it stopped.
    """
    settings = load_settings()
    jira = build_jira_client(settings)
    extractor = build_attachment_extractor()
    sem = asyncio.Semaphore(concurrency)
    records: list[dict] = list(done_records or [])
    done = {r["ticketId"] for r in records}
    todo = [t for t in ticket_ids if t not in done]
    progress = {"n": 0, "total": len(todo)}

    async def _one(ticket_id: str) -> list[dict]:
        out: list[dict] = []
        try:
            ticket = await asyncio.wait_for(jira.fetch_ticket(ticket_id), timeout=ticket_timeout)
        except Exception as exc:  # a bad/slow ticket must not abort the batch - record it
            reason = f"{type(exc).__name__}: {exc}" or type(exc).__name__
            print(f"  {ticket_id}: FETCH ERROR {reason}")
            return [{
                "ticketId": ticket_id, "kind": "fetch_error", "filename": "(ticket fetch)",
                "ext": "(error)", "mimeType": "", "sizeBytes": 0, "charCount": 0, "tokenEst": 0,
                "supported": False, "ideaCard": False, "selected": False, "extractError": reason,
            }]
        desc = ticket.description or ""
        out.append({
            "ticketId": ticket_id, "kind": "description", "filename": "(description)",
            "ext": "(description)", "mimeType": "", "sizeBytes": len(desc.encode("utf-8")),
            "charCount": len(desc), "tokenEst": estimate_tokens(desc),
            "supported": True, "ideaCard": False, "selected": False, "extractError": "",
        })
        # Which attachments condense would actually use: idea-card-first, else top-4 supported.
        chosen = select_attachments(ticket.attachments)
        selected_names = {a.filename for a in ([chosen.idea_card] if chosen.idea_card else chosen.fallback)}
        for att in ticket.attachments:
            rec = {
                "ticketId": ticket_id, "kind": "attachment", "filename": att.filename,
                "ext": _ext(att.filename), "mimeType": att.mime_type,
                "sizeBytes": int(att.size_bytes or 0), "charCount": 0, "tokenEst": 0,
                "supported": is_supported(att.filename), "ideaCard": is_idea_card(att.filename),
                "selected": att.filename in selected_names,  # condense would extract this one
                "extractError": "",
            }
            if rec["supported"]:
                try:
                    # bound BOTH the download and the (native) extract so a stall can't hang the slot
                    content = await asyncio.wait_for(jira.download_attachment(att), timeout=ticket_timeout)
                    text = await asyncio.wait_for(
                        asyncio.to_thread(extractor.extract, att.filename, content), timeout=ticket_timeout
                    )
                    rec["charCount"] = len(text or "")
                    rec["tokenEst"] = estimate_tokens(text or "")
                except Exception as exc:
                    rec["extractError"] = f"{type(exc).__name__}: {exc}" or type(exc).__name__
                    print(f"  {ticket_id} / {att.filename}: EXTRACT ERROR {rec['extractError']}")
            out.append(rec)
        return out

    async def _guarded(ticket_id: str) -> None:
        async with sem:
            out = await _one(ticket_id)
        records.extend(out)
        progress["n"] += 1
        n_att = sum(1 for r in out if r["kind"] == "attachment")
        print(f"[{progress['n']}/{progress['total']}] {ticket_id}: {n_att} attachments")
        if checkpoint_path is not None and progress["n"] % checkpoint_every == 0:
            checkpoint_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    if done:
        print(f"resuming: {len(done)} tickets already collected, {len(todo)} to go")
    await asyncio.gather(*(_guarded(t) for t in todo))
    if checkpoint_path is not None:  # final flush
        checkpoint_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


# ---------------------------------------------------------------- analysis (pandas)

def to_frames(records: list[dict]):
    """Return (attachments_df, tickets_df). Requires pandas (eda extra)."""
    import pandas as pd

    df = pd.DataFrame(records)
    att = df[df["kind"] == "attachment"].copy()
    desc = df[df["kind"] == "description"].copy()

    per_ticket = att.groupby("ticketId").agg(
        attachmentCount=("filename", "count"),
        supportedCount=("supported", "sum"),
        attachmentBytes=("sizeBytes", "sum"),
        attachmentTokens=("tokenEst", "sum"),
        attachmentChars=("charCount", "sum"),
        hasIdeaCard=("ideaCard", "max"),
    )
    desc_idx = desc.set_index("ticketId")
    per_ticket["descriptionChars"] = desc_idx["charCount"].reindex(per_ticket.index).fillna(0).astype(int)
    per_ticket["descriptionTokens"] = desc_idx["tokenEst"].reindex(per_ticket.index).fillna(0).astype(int)
    per_ticket["combinedTokens"] = per_ticket["attachmentTokens"] + per_ticket["descriptionTokens"]
    # tickets with attachments listed in the issue but none fetched still appear via desc only:
    only_desc = desc_idx.index.difference(per_ticket.index)
    if len(only_desc):
        import pandas as pd  # noqa: F811
        extra = pd.DataFrame(index=only_desc)
        extra["attachmentCount"] = 0
        extra["supportedCount"] = 0
        extra["attachmentBytes"] = 0
        extra["attachmentTokens"] = 0
        extra["attachmentChars"] = 0
        extra["hasIdeaCard"] = False
        extra["descriptionChars"] = desc_idx["charCount"].reindex(only_desc).fillna(0).astype(int)
        extra["descriptionTokens"] = desc_idx["tokenEst"].reindex(only_desc).fillna(0).astype(int)
        extra["combinedTokens"] = extra["descriptionTokens"]
        per_ticket = pd.concat([per_ticket, extra])
    return att, per_ticket.reset_index().rename(columns={"index": "ticketId"})


def _save(fig, charts_dir: Path, name: str) -> str:
    charts_dir.mkdir(parents=True, exist_ok=True)
    path = charts_dir / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    return str(path)


def build_charts(att, tickets, charts_dir: Path) -> tuple[dict, dict]:
    """Compute the metric tables + render the charts. Returns (stats, chart_paths)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.figsize": (8, 4.5), "axes.grid": True, "grid.alpha": 0.3})
    stats: dict = {}
    charts: dict = {}

    # 0. attachment presence: tickets WITH vs WITHOUT any attachment
    n = int(len(tickets))
    without = int((tickets["attachmentCount"] == 0).sum())
    with_att = n - without
    stats["attachment_presence"] = {
        "tickets_total": n,
        "tickets_with_attachments": with_att,
        "tickets_without_attachments": without,
        "pct_without": round(100.0 * without / max(1, n), 1),
    }
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(["with attachments", "no attachments"], [with_att, without], color=["#4C78A8", "#E45756"])
    for i, v in enumerate([with_att, without]):
        ax.text(i, v, str(v), ha="center", va="bottom")
    ax.set(title="Tickets with vs without attachments", ylabel="# tickets")
    charts["attachment_presence"] = _save(fig, charts_dir, "attachment_presence"); plt.close(fig)

    # 1. attachments per ticket
    counts = tickets["attachmentCount"]
    stats["attachments_per_ticket"] = {
        "tickets": int(len(tickets)), "mean": round(float(counts.mean()), 2),
        "median": float(counts.median()), "max": int(counts.max()),
        "with_zero": int((counts == 0).sum()),
    }
    fig, ax = plt.subplots()
    counts.value_counts().sort_index().plot(kind="bar", ax=ax, color="#4C78A8")
    ax.set(title="Attachments per ticket", xlabel="# attachments", ylabel="# tickets")
    charts["attachments_per_ticket"] = _save(fig, charts_dir, "attachments_per_ticket"); plt.close(fig)

    # 2. file types
    types = att["ext"].value_counts()
    stats["file_types"] = {k: int(v) for k, v in types.items()}
    stats["most_common_type"] = types.index[0] if len(types) else None
    fig, ax = plt.subplots()
    types.plot(kind="bar", ax=ax, color="#F58518")
    ax.set(title="Attachment file types", xlabel="extension", ylabel="# attachments")
    charts["file_types"] = _save(fig, charts_dir, "file_types"); plt.close(fig)

    # 3. attachment sizes (KB) — per attachment AND total per ticket
    kb = att["sizeBytes"] / 1024.0
    per_ticket_kb = tickets["attachmentBytes"] / 1024.0
    stats["attachment_size_kb"] = {
        # per single attachment
        "per_attachment_mean": round(float(kb.mean()), 1),
        "per_attachment_median": round(float(kb.median()), 1),
        "per_attachment_p90": round(float(kb.quantile(0.9)), 1),
        "per_attachment_max": round(float(kb.max()), 1),
        # total across a ticket's attachments
        "per_ticket_total_mean": round(float(per_ticket_kb.mean()), 1),
        "per_ticket_total_median": round(float(per_ticket_kb.median()), 1),
        "per_ticket_total_max": round(float(per_ticket_kb.max()), 1),
        "all_attachments_total_mb": round(float(att["sizeBytes"].sum()) / 1_048_576, 1),
    }
    fig, ax = plt.subplots()
    ax.hist(kb.clip(upper=kb.quantile(0.99)), bins=40, color="#54A24B")
    ax.set(title="Attachment size (KB, clipped at p99)", xlabel="KB", ylabel="# attachments")
    charts["attachment_size_kb"] = _save(fig, charts_dir, "attachment_size_kb"); plt.close(fig)

    # 4. extracted char counts (supported only)
    sup = att[att["supported"] & (att["charCount"] > 0)]
    if len(sup):
        cc = sup["charCount"]
        stats["extracted_chars"] = {
            "mean": int(cc.mean()), "median": int(cc.median()), "max": int(cc.max()),
            "p90": int(cc.quantile(0.9)),
        }
        fig, ax = plt.subplots()
        ax.hist(cc.clip(upper=cc.quantile(0.99)), bins=40, color="#B279A2")
        ax.set(title="Extracted characters per attachment (p99 clip)", xlabel="chars", ylabel="# attachments")
        charts["extracted_chars"] = _save(fig, charts_dir, "extracted_chars"); plt.close(fig)

    # 5. description length
    dc = tickets["descriptionChars"]
    stats["description_chars"] = {
        "mean": int(dc.mean()), "median": int(dc.median()), "max": int(dc.max()),
        "empty": int((dc == 0).sum()),
    }
    fig, ax = plt.subplots()
    ax.hist(dc.clip(upper=dc.quantile(0.99)), bins=40, color="#E45756")
    ax.set(title="Jira description length (chars, p99 clip)", xlabel="chars", ylabel="# tickets")
    charts["description_chars"] = _save(fig, charts_dir, "description_chars"); plt.close(fig)

    # 6. combined tokens per ticket vs the budget
    ct = tickets["combinedTokens"]
    over = int((ct > TOKEN_BUDGET).sum())
    stats["combined_tokens"] = {
        "budget": TOKEN_BUDGET, "mean": int(ct.mean()), "median": int(ct.median()),
        "max": int(ct.max()), "over_budget": over,
        "over_budget_pct": round(100.0 * over / max(1, len(ct)), 1),
    }
    fig, ax = plt.subplots()
    ax.hist(ct.clip(upper=ct.quantile(0.99)), bins=40, color="#72B7B2")
    ax.axvline(TOKEN_BUDGET, color="red", linestyle="--", label=f"{TOKEN_BUDGET:,} budget")
    ax.set(title="Combined tokens per ticket (description + attachments)", xlabel="tokens", ylabel="# tickets")
    ax.legend()
    charts["combined_tokens"] = _save(fig, charts_dir, "combined_tokens"); plt.close(fig)

    # 7. idea-card / supported coverage + what condense would actually select
    sel = att["selected"] if "selected" in att.columns else att.get("selected", False)
    stats["coverage"] = {
        "tickets_with_idea_card": int(tickets["hasIdeaCard"].sum()),
        "supported_attachments": int(att["supported"].sum()),
        "unsupported_attachments": int((~att["supported"]).sum()),
        "attachments_condense_selects": int(att["selected"].sum()) if "selected" in att.columns else 0,
        "attachments_ignored": int((~att["selected"]).sum()) if "selected" in att.columns else 0,
        "extract_failures": int((att["extractError"] != "").sum()),
    }
    return stats, charts


def collect_failures(records: list[dict]) -> list[dict]:
    """Every fetch/extract failure, for debugging: {ticketId, filename, kind, reason}."""
    out: list[dict] = []
    for r in records:
        reason = r.get("extractError") or ""
        if reason:
            out.append({
                "ticketId": r.get("ticketId", ""), "filename": r.get("filename", ""),
                "kind": r.get("kind", ""), "ext": r.get("ext", ""), "reason": reason,
            })
    return out


# ---------------------------------------------------------------- docx export

def _metric_table(doc, rows: dict) -> None:
    """A clean 2-column metric/value table with a shaded header."""
    table = doc.add_table(rows=1, cols=2)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text = "Metric", "Value"
    for k, v in rows.items():
        cells = table.add_row().cells
        cells[0].text = str(k).replace("_", " ")
        cells[1].text = f"{v:,}" if isinstance(v, int) else str(v)
    doc.add_paragraph()


def _highlights(stats: dict, n_tickets: int) -> dict:
    """The headline numbers, pulled from the per-section stats for the summary table."""
    pres = stats.get("attachment_presence", {})
    apt = stats.get("attachments_per_ticket", {})
    size = stats.get("attachment_size_kb", {})
    ct = stats.get("combined_tokens", {})
    cov = stats.get("coverage", {})
    return {
        "Tickets analyzed": n_tickets,
        "Tickets without attachments": f"{pres.get('tickets_without_attachments', '?')} "
                                       f"({pres.get('pct_without', '?')}%)",
        "Avg attachments per ticket": apt.get("mean", "?"),
        "Most common file type": stats.get("most_common_type", "?"),
        "Avg attachment size (KB)": size.get("per_attachment_mean", "?"),
        "Avg total attachment size per ticket (KB)": size.get("per_ticket_total_mean", "?"),
        "Tickets over token budget": f"{ct.get('over_budget', '?')} "
                                     f"({ct.get('over_budget_pct', '?')}%) of {ct.get('budget', '?'):,}",
        "Tickets with an idea card": cov.get("tickets_with_idea_card", "?"),
    }


def build_docx(stats: dict, charts: dict, out_path: Path, *, n_tickets: int,
               failures: list[dict] | None = None) -> None:
    from datetime import date

    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    doc = Document()
    title = doc.add_heading("Attachments EDA — Phase 1", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(f"IDMT ingestion · {n_tickets} tickets · {date.today().isoformat()}")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in sub.runs:
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_heading("Highlights", level=1)
    doc.add_paragraph(
        "Profile of attachments across the historical IDMT tickets. These numbers drive "
        "condense/ingestion sizing: how many attachments to pull, and the character/token budgets."
    )
    _metric_table(doc, _highlights(stats, n_tickets))

    # title, stat key, one-line explanation of what the chart answers
    sections = [
        ("1. Tickets with vs without attachments", "attachment_presence",
         "How many tickets carry no attachment at all — those fall back to the Jira description."),
        ("2. Attachments per ticket", "attachments_per_ticket",
         "Distribution of attachment count per ticket; informs the top-N selection cap."),
        ("3. File types", "file_types",
         "What attachment formats appear and which dominates (idea cards are usually PPT/PPTX)."),
        ("4. Attachment size", "attachment_size_kb",
         "Per-attachment size and the total payload per ticket; informs the pre-download size cap."),
        ("5. Extracted characters per attachment", "extracted_chars",
         "How much text each supported attachment yields after extraction."),
        ("6. Jira description length", "description_chars",
         "Typical Jira description length — the fallback context when no idea card exists."),
        ("7. Combined tokens per ticket vs budget", "combined_tokens",
         "How many tickets exceed the token budget once description + all attachment text is combined."),
        ("8. Coverage", "coverage",
         "Idea-card presence, supported vs unsupported attachments, and extraction failures."),
    ]
    doc.add_page_break()
    for title_text, key, blurb in sections:
        doc.add_heading(title_text, level=1)
        doc.add_paragraph(blurb)
        if key in charts and Path(charts[key]).exists():
            doc.add_picture(charts[key], width=Inches(6.0))
        if key in stats:
            _metric_table(doc, stats[key])

    # 9. Failures - ticket id + attachment + reason, for debugging
    doc.add_heading("9. Fetch / extract failures", level=1)
    if failures:
        doc.add_paragraph(
            f"{len(failures)} attachment(s)/ticket(s) failed to fetch or extract (timeout, "
            "download error, or unparseable file). Listed for debugging."
        )
        table = doc.add_table(rows=1, cols=3)
        table.style = "Light Grid Accent 1"
        for cell, label in zip(table.rows[0].cells, ("Ticket", "Attachment", "Reason")):
            cell.text = label
        for f in failures:
            cells = table.add_row().cells
            cells[0].text = str(f.get("ticketId", ""))
            cells[1].text = str(f.get("filename", ""))
            cells[2].text = str(f.get("reason", ""))[:200]
    else:
        doc.add_paragraph("No fetch or extract failures.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


# ---------------------------------------------------------------- CLI

async def _main(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "attachments_raw.json"

    ticket_ids = load_ticket_ids(args.tickets)
    have = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else []
    collected_ids = {r["ticketId"] for r in have}
    remaining = [t for t in ticket_ids if t not in collected_ids]

    if args.use_cache and not remaining:
        records = have
        print(f"loaded {len(records)} cached records ({len(collected_ids)} tickets) from {cache}")
    else:
        # Always resume from whatever is already cached, checkpointing as we go, so a stall/stop
        # never loses progress - re-run the same command to continue from where it stopped.
        print(f"collecting {len(remaining)}/{len(ticket_ids)} tickets "
              f"(concurrency={args.concurrency}, timeout={args.ticket_timeout}s, "
              f"checkpoint every {args.checkpoint_every}); cache: {cache}")
        records = await collect(
            ticket_ids, concurrency=args.concurrency, ticket_timeout=args.ticket_timeout,
            done_records=have, checkpoint_path=cache, checkpoint_every=args.checkpoint_every,
        )
        print(f"collected {len({r['ticketId'] for r in records})} tickets -> {cache}")

    att, tickets = to_frames(records)
    stats, charts = build_charts(att, tickets, out / "charts")
    (out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"\nstats -> {out/'stats.json'}\ncharts -> {out/'charts'}/")
    print(json.dumps(stats, indent=2))

    # Failures (ticket id + attachment + reason) for debugging - own file + console.
    failures = collect_failures(records)
    (out / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    print(f"\n{len(failures)} fetch/extract failures -> {out/'failures.json'}")
    for f in failures[:30]:
        print(f"  {f['ticketId']}  {f['filename']}  -> {f['reason']}")
    if len(failures) > 30:
        print(f"  ... and {len(failures) - 30} more (see failures.json)")

    if args.docx:
        docx_path = out / "attachments_eda.docx"
        build_docx(stats, charts, docx_path, n_tickets=int(len(tickets)), failures=failures)
        print(f"docx -> {docx_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tickets", help="text file with one IDMT id per line")
    parser.add_argument("--out", default="out/eda/attachments")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--ticket-timeout", type=float, default=90.0,
                        help="seconds before a slow fetch/download/extract is abandoned (per call)")
    parser.add_argument("--checkpoint-every", type=int, default=10,
                        help="flush the cache every N tickets so a stop never loses progress")
    parser.add_argument("--use-cache", action="store_true",
                        help="if every ticket is already cached, skip collection; otherwise resume")
    parser.add_argument("--docx", action="store_true", help="also write the .docx report")
    asyncio.run(_main(parser.parse_args()))
