"""Search credential selection: service principal preferred, API key fallback.

Skips when the 'search' extra (azure-identity) is not installed.
"""

from __future__ import annotations

import pytest

from teg.config.settings import Settings

pytest.importorskip("azure.identity")

from teg.integrations.search.credential import build_search_credential, search_bearer_token


def test_prefers_service_principal() -> None:
    from azure.identity.aio import ClientSecretCredential

    settings = Settings(
        azure_tenant_id="t", azure_client_id="c", azure_client_secret="s", search_api_key="key"
    )
    cred = build_search_credential(settings)
    assert isinstance(cred, ClientSecretCredential)  # SP wins even when a key is set


def test_falls_back_to_api_key() -> None:
    from azure.core.credentials import AzureKeyCredential

    cred = build_search_credential(Settings(search_api_key="key"))
    assert isinstance(cred, AzureKeyCredential)
    assert cred.key == "key"


def test_no_credential_raises() -> None:
    with pytest.raises(ValueError):
        build_search_credential(Settings())  # neither SP nor key


def test_bearer_token_none_without_service_principal() -> None:
    assert search_bearer_token(Settings(search_api_key="key")) is None
