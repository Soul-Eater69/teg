"""Environment-driven configuration.

All external endpoints/keys come from the environment (or a local .env). No secrets
in code. Inject a Settings instance; never read os.environ deep in the call tree.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEG_", env_file=".env", extra="ignore")

    # Jira
    jira_base_url: str = ""
    jira_token: str = ""  # Personal Access Token (Bearer)
    jira_api_version: str = "2"
    jira_verify_ssl: bool = False
    jira_timeout_seconds: float = 30.0

    # Azure AI Search (idp_idmt_data unified index)
    search_endpoint: str = ""
    search_api_key: str = ""
    search_index: str = "idp_idmt_data"

    # Cosmos (lineage, ground truth, governed catalogues)
    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database: str = ""

    # LLM (IDP OpenAI-compatible gateway)
    llm_base_url: str = ""
    llm_completion_path: str = "/api/v1/chatcompletions"
    llm_model: str = "gpt-5-mini-idp"
    llm_app_id: str = ""
    llm_api_version: str = "2024-04-01-preview"
    llm_reasoning_effort: str = "low"
    llm_max_output_tokens: int | None = None
    llm_timeout_seconds: float = 60.0
    llm_verify_ssl: bool = False

    # Condense (fallback path only; idea card is always used in full)
    condense_doc_char_budget: int = 20_000  # total chars across fallback docs (split per doc)
    condense_max_attachments: int = 4  # top-N fallback when no idea card
    condense_max_attachment_bytes: int = 10_000_000  # skip larger fallback files pre-download
    condense_min_doc_chars: int = 200  # drop fallback docs that extract to less than this

    # IDP auth (token endpoint for the LLM gateway)
    idp_auth_url: str = ""
    idp_client_id: str = ""
    idp_client_secret: str = ""
    idp_user: str = ""
    idp_password: str = ""


def load_settings() -> Settings:
    return Settings()
