"""Print the IDP LLM gateway bearer token.

Fetches a fresh JWT from the IDP token endpoint using the same settings the LLM client uses, and
prints it. Useful for manually testing the gateway (e.g. pasting the token into another client).

Run:
    uv run python -m scripts.print_token
    uv run python -m scripts.print_token --header   # print as "Authorization: Bearer <token>"
"""

from __future__ import annotations

import argparse
import asyncio

from teg.config.settings import load_settings
from teg.integrations.llm.idp_auth import IDPCustomAuth


async def main(as_header: bool) -> None:
    settings = load_settings()
    auth = IDPCustomAuth(
        app_id=settings.llm_app_id,
        auth_url=settings.idp_auth_url,
        client_id=settings.idp_client_id,
        client_secret=settings.idp_client_secret,
        user=settings.idp_user,
        password=settings.idp_password,
        verify_ssl=settings.llm_verify_ssl,
    )
    token = await auth._fetch_token()
    if as_header:
        print(f"Authorization: Bearer {token}")
        print(f"app-id: {settings.llm_app_id}")
    else:
        print(token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--header", action="store_true", help="print as HTTP auth headers")
    args = parser.parse_args()
    asyncio.run(main(args.header))
