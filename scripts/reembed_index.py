"""Re-embed the historical index docs with a chosen retrieval representation - from LOCAL files.

The index is summary-embedded by default. To test whether we can drop summarization entirely,
re-embed every historical doc on the ticket's RAW text (truncated to a token budget) instead -
no Jira re-fetch, no re-condense: rawText already lives in cosmos_idmt.json.

  --repr raw7k   searchText = rawText truncated to --budget tokens, re-embedded
  --repr summary searchText = the existing summary retrieval text, re-embedded (restore)

Reversible: run with --repr summary to put the summary index back, also from local files.

Usage:
  uv run python scripts/reembed_index.py --repr raw7k --budget 7000 --upload
  uv run python scripts/reembed_index.py --repr summary --upload          # restore
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import tiktoken

from teg.config.settings import load_settings
from teg.integrations.embeddings import build_embeddings_client
from teg.ingestion.upload.search_uploader import build_search_uploader

# The embedding model has a hard ~8191-token input limit; truncate by ACTUAL tokens (cl100k_base,
# the text-embedding-3 tokenizer) not chars - a chars heuristic overshoots on dense text and 400s.
_ENC = tiktoken.get_encoding("cl100k_base")
_EMBED_TOKEN_CAP = 8000  # safety ceiling under the model limit, regardless of --budget


def _truncate_tokens(text: str, max_tokens: int) -> str:
    toks = _ENC.encode(text)
    return text if len(toks) <= max_tokens else _ENC.decode(toks[:max_tokens])


def _raw_by_source(idmt_docs: list[dict]) -> dict[str, str]:
    """{sourceId|key: rawText} from the local IDMT docs (no Jira needed)."""
    out: dict[str, str] = {}
    for d in idmt_docs:
        raw = (d.get("properties") or {}).get("rawText") or ""
        for k in (d.get("sourceId"), d.get("key")):
            if k:
                out[str(k)] = raw
    return out


def _search_text(doc: dict, repr_: str, budget: int, raw_by_source: dict[str, str]) -> str:
    if repr_ == "summary":
        return _truncate_tokens(str(doc.get("searchText") or ""), _EMBED_TOKEN_CAP)
    raw = raw_by_source.get(str(doc.get("sourceId"))) or raw_by_source.get(str(doc.get("key"))) or ""
    return _truncate_tokens(raw, min(budget, _EMBED_TOKEN_CAP))  # token-accurate, under the model cap


async def main(args: argparse.Namespace) -> None:
    idmt_docs = json.loads(Path(args.idmt).read_text(encoding="utf-8"))
    historical = json.loads(Path(args.historical).read_text(encoding="utf-8"))
    raw_by_source = _raw_by_source(idmt_docs)

    texts = [_search_text(d, args.repr, args.budget, raw_by_source) for d in historical]
    empty = sum(1 for t in texts if not t.strip())
    print(f"{len(historical)} docs | repr={args.repr}"
          + (f" budget={args.budget}tok" if args.repr == "raw7k" else "")
          + (f" | WARNING {empty} have empty searchText" if empty else ""))

    settings = load_settings()
    embeddings = build_embeddings_client(settings)
    vectors: list[list[float]] = []
    for i in range(0, len(texts), args.batch):
        chunk = texts[i:i + args.batch]
        vectors.extend(await embeddings.embed_many(chunk))
        print(f"  embedded {min(i + args.batch, len(texts))}/{len(texts)}")

    for doc, text, vec in zip(historical, texts, vectors):
        doc["searchText"] = text
        doc["content_vector"] = vec

    out = Path(args.out or Path(args.historical).with_name(f"index_historical.{args.repr}.json"))
    out.write_text(json.dumps(historical, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {out}")

    if args.upload:
        uploader = build_search_uploader(settings)
        try:
            report = await uploader.upload(historical)
        finally:
            await uploader.close()
        print(f"upserted {report.succeeded}/{len(historical)} docs -> {settings.search_index}")
        for f in report.failures:
            print(f"  FAILED {f.document_id}: [{f.status_code}] {f.error_message}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Re-embed historical index docs from local files.")
    p.add_argument("--idmt", default="out/idmt/cosmos_idmt.json", help="local IDMT docs (rawText source)")
    p.add_argument("--historical", default="out/idmt/index_historical.json", help="index docs to re-embed")
    p.add_argument("--repr", choices=["summary", "raw7k"], default="raw7k")
    p.add_argument("--budget", type=int, default=7000, help="raw token budget for --repr raw7k")
    p.add_argument("--out", default="", help="output path (default index_historical.<repr>.json)")
    p.add_argument("--batch", type=int, default=16, help="embeddings batch size")
    p.add_argument("--upload", action="store_true", help="upsert into the search index after embedding")
    asyncio.run(main(p.parse_args()))
