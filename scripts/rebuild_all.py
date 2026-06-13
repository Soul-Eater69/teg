"""Full clean rebuild: recreate the index, load the VS catalogue, fresh-ingest the tickets.

One command for a from-scratch rebuild after schema changes. Runs, in order:
  1. create_index --recreate        (DROP + create the lean idp_teg_data index - wipes all docs)
  2. generate_vs_catalogue --upload (VS catalogue lane -> index, embedded)
  3. ingest_tickets --fresh         (tickets -> cosmos docs + historic lane -> index)

Destructive (step 1 drops the index), so it requires --yes. Needs the 'search' + 'extract' extras
and Jira/IDP creds in .env.

Usage:
  uv run python scripts/rebuild_all.py data/tickets_eda.txt --yes
  uv run python scripts/rebuild_all.py data/tickets_eda.txt --yes --concurrency 4
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import create_index
import generate_vs_catalogue
import ingest_tickets


async def main(args) -> None:
    if not args.yes:
        raise SystemExit("this DROPS and rebuilds the index. Re-run with --yes to confirm.")

    print("\n" + "=" * 70 + "\n[1/3] RECREATE INDEX (drops all docs)\n" + "=" * 70)
    await create_index.main(args.definition, recreate=True)

    if args.with_vs_index:
        print("\n" + "=" * 70 + "\n[2/3] VS CATALOGUE -> INDEX\n" + "=" * 70)
        await generate_vs_catalogue.main(args.catalogue, args.catalogue_out, embed=True, upload=True)
    else:
        print("\n" + "=" * 70 + "\n[2/3] VS CATALOGUE -> INDEX  (SKIPPED - VS now comes from the "
              "catalogue file; index holds only historic docs)\n" + "=" * 70)

    print("\n" + "=" * 70 + "\n[3/3] FRESH TICKET INGEST -> COSMOS + HISTORIC INDEX\n" + "=" * 70)
    await ingest_tickets.main(
        args.tickets_file, args.catalogue, args.out, upload=True,
        concurrency=args.concurrency, fresh=True,
    )

    print("\n" + "=" * 70 + "\nDONE. Verify with: uv run python scripts/show_index.py\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tickets_file", help="text file with one ticket id per line")
    parser.add_argument("--yes", action="store_true", help="confirm the destructive index recreate")
    parser.add_argument("--with-vs-index", action="store_true",
                        help="also upload the VS catalogue to the index (legacy; VS now comes from "
                             "the catalogue file, so this is off by default)")
    parser.add_argument("--definition", default="data/idp_teg_data_index.json")
    parser.add_argument("--catalogue", default="data/value_stream_capability_map.json")
    parser.add_argument("--catalogue-out", dest="catalogue_out", default="out/catalogue")
    parser.add_argument("--out", default="out/idmt")
    parser.add_argument("--concurrency", type=int, default=4)
    asyncio.run(main(parser.parse_args()))
