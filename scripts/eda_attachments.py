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

from teg.condense.attachment_ranker import is_idea_card, is_supported
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


async def collect(ticket_ids: list[str], *, concurrency: int = 4) -> list[dict]:
    """One record per (ticket, attachment), plus a synthetic 'description' pseudo-attachment.

    Each record: ticketId, kind (attachment|description), filename, ext, mimeType, sizeBytes,
    charCount, tokenEst, supported, ideaCard, extractError. Failures are recorded, not fatal.
    """
    settings = load_settings()
    jira = build_jira_client(settings)
    extractor = build_attachment_extractor()
    sem = asyncio.Semaphore(concurrency)
    records: list[dict] = []

    async def _one(ticket_id: str) -> None:
        async with sem:
            try:
                ticket = await jira.fetch_ticket(ticket_id)
            except Exception as exc:  # a bad ticket must not abort the batch
                print(f"{ticket_id}: FETCH ERROR {type(exc).__name__}: {exc}")
                return
            desc = ticket.description or ""
            records.append({
                "ticketId": ticket_id, "kind": "description", "filename": "(description)",
                "ext": "(description)", "mimeType": "", "sizeBytes": len(desc.encode("utf-8")),
                "charCount": len(desc), "tokenEst": estimate_tokens(desc),
                "supported": True, "ideaCard": False, "extractError": "",
            })
            for att in ticket.attachments:
                rec = {
                    "ticketId": ticket_id, "kind": "attachment", "filename": att.filename,
                    "ext": _ext(att.filename), "mimeType": att.mime_type,
                    "sizeBytes": int(att.size_bytes or 0), "charCount": 0, "tokenEst": 0,
                    "supported": is_supported(att.filename), "ideaCard": is_idea_card(att.filename),
                    "extractError": "",
                }
                if rec["supported"]:
                    try:
                        content = await jira.download_attachment(att)
                        text = await asyncio.to_thread(extractor.extract, att.filename, content)
                        rec["charCount"] = len(text or "")
                        rec["tokenEst"] = estimate_tokens(text or "")
                    except Exception as exc:
                        rec["extractError"] = f"{type(exc).__name__}: {exc}"
                records.append(rec)
            print(f"{ticket_id}: {len(ticket.attachments)} attachments")

    await asyncio.gather(*(_one(t) for t in ticket_ids))
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

    # 7. idea-card / supported coverage
    stats["coverage"] = {
        "tickets_with_idea_card": int(tickets["hasIdeaCard"].sum()),
        "supported_attachments": int(att["supported"].sum()),
        "unsupported_attachments": int((~att["supported"]).sum()),
        "extract_failures": int((att["extractError"] != "").sum()),
    }
    return stats, charts


# ---------------------------------------------------------------- docx export

def build_docx(stats: dict, charts: dict, out_path: Path, *, n_tickets: int) -> None:
    from docx import Document
    from docx.shared import Inches

    doc = Document()
    doc.add_heading("Attachments EDA — Phase 1", level=0)
    doc.add_paragraph(
        f"Profile of attachments across {n_tickets} historical IDMT tickets. Figures and metrics "
        "below drive condense/ingestion sizing (attachment selection, char/token budgets)."
    )

    sections = [
        ("0. Tickets with vs without attachments", "attachment_presence"),
        ("1. Attachments per ticket", "attachments_per_ticket"),
        ("2. File types", "file_types"),
        ("3. Attachment size", "attachment_size_kb"),
        ("4. Extracted characters per attachment", "extracted_chars"),
        ("5. Jira description length", "description_chars"),
        ("6. Combined tokens per ticket vs budget", "combined_tokens"),
    ]
    for title, key in sections:
        doc.add_heading(title, level=1)
        if key in stats:
            for k, v in stats[key].items():
                doc.add_paragraph(f"{k}: {v}", style="List Bullet")
        if key in charts and Path(charts[key]).exists():
            doc.add_picture(charts[key], width=Inches(6.0))

    doc.add_heading("7. Coverage", level=1)
    for k, v in stats.get("coverage", {}).items():
        doc.add_paragraph(f"{k}: {v}", style="List Bullet")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


# ---------------------------------------------------------------- CLI

async def _main(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "attachments_raw.json"

    if args.use_cache and cache.exists():
        records = json.loads(cache.read_text(encoding="utf-8"))
        print(f"loaded {len(records)} cached records from {cache}")
    else:
        ticket_ids = load_ticket_ids(args.tickets)
        print(f"collecting attachments for {len(ticket_ids)} tickets (concurrency={args.concurrency})")
        records = await collect(ticket_ids, concurrency=args.concurrency)
        cache.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {len(records)} records -> {cache}")

    att, tickets = to_frames(records)
    stats, charts = build_charts(att, tickets, out / "charts")
    (out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"\nstats -> {out/'stats.json'}\ncharts -> {out/'charts'}/")
    print(json.dumps(stats, indent=2))

    if args.docx:
        docx_path = out / "attachments_eda.docx"
        build_docx(stats, charts, docx_path, n_tickets=int(len(tickets)))
        print(f"docx -> {docx_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tickets", help="text file with one IDMT id per line")
    parser.add_argument("--out", default="out/eda/attachments")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--use-cache", action="store_true", help="reuse <out>/attachments_raw.json")
    parser.add_argument("--docx", action="store_true", help="also write the .docx report")
    asyncio.run(_main(parser.parse_args()))
