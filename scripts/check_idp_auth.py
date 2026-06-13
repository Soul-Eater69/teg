"""Isolate the IDP token fetch and print why it succeeds or fails.

The ingest's 401s come from the token POST to idp_auth_url, but raise_for_status() hides
the STS's reason. This does only that POST and prints the status + response body (which
usually says invalid_client / bad password / expired) plus which settings are populated
(values masked). No tickets, no LLM, no Azure.

Usage (needs IDP creds in .env):
  uv run python scripts/check_idp_auth.py
"""

from __future__ import annotations

import asyncio

import httpx

from teg.config.settings import load_settings


def _mask(value: str) -> str:
    value = str(value or "")
    if not value:
        return "(empty)"
    return f"set, len={len(value)}, tail=...{value[-4:]}" if len(value) > 4 else "set (short)"


async def main() -> None:
    s = load_settings()
    print("IDP settings:")
    print(f"  idp_auth_url     = {s.idp_auth_url or '(empty)'}")
    print(f"  idp_client_id    = {_mask(s.idp_client_id)}")
    print(f"  idp_client_secret= {_mask(s.idp_client_secret)}")
    print(f"  idp_user         = {s.idp_user or '(empty)'}")
    print(f"  idp_password     = {_mask(s.idp_password)}")
    print(f"  llm_app_id       = {s.llm_app_id or '(empty)'}\n")

    if not s.idp_auth_url:
        raise SystemExit("idp_auth_url is empty - set it in .env")

    headers = {
        "Accept": "*/*",
        "ClientId": s.idp_client_id,
        "ClientSecret": s.idp_client_secret,
        "scope": "profile openid roles permissions",
    }
    body = {"username": s.idp_user, "password": s.idp_password}
    async with httpx.AsyncClient(verify=s.llm_verify_ssl) as client:
        resp = await client.post(s.idp_auth_url, headers=headers, json=body)

    print(f"POST {s.idp_auth_url}\n  -> HTTP {resp.status_code}")
    body_text = resp.text
    print(f"  body: {body_text[:600]}{' ...' if len(body_text) > 600 else ''}")
    if resp.status_code == 200:
        token = (resp.json() or {}).get("jwt_token")
        print("  jwt_token present:" , bool(token), f"(len={len(token)})" if token else "")
        print("\nAuth OK - the 401 is not the credentials themselves." if token
              else "\n200 but no jwt_token - response shape changed.")
    else:
        print("\nThe STS rejected these credentials. Check idp_client_secret / idp_password "
              "for expiry/rotation, and that idp_auth_url is the current endpoint.")


if __name__ == "__main__":
    asyncio.run(main())
