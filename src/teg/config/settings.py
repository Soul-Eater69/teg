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

    # Azure AI Search (two indices for now; unify later)
    search_endpoint: str = ""
    search_api_key: str = ""
    search_index_value_stream: str = "idp_kg_data_test"
    search_index_historical: str = "idp_idmt_data"
    search_vector_field: str = "content_vector"
    search_semantic_config: str = "default"

    # Value Stream retrieval / review-window tuning (-> ValueStreamConfig)
    vs_semantic_fetch_k: int = 50
    vs_historical_fetch_k: int = 6
    vs_llm_candidate_window: int = 18
    vs_window_headroom: int = 8
    vs_max_supporting_tickets: int = 2

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

    # Embeddings (same IDP gateway + auth as the LLM)
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    embedding_path: str = "/api/v1/embeddings"
    embedding_api_version: str = "2024-06-01"


def load_settings() -> Settings:
    return Settings()
