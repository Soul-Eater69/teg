"""Layered configuration.

Three tiers, highest precedence first:
  1. .env (gitignored)                -> secrets only: tokens, keys, passwords, secret
  2. config/settings.local.yaml (gi)  -> environment non-secrets: endpoints, ids, user, db
  3. config/settings.yaml (committed) -> shared non-secrets: model, index, paths, knobs

Env still overrides everything (deployment flexibility), but by convention holds only
secrets. Non-secret config does NOT live in env. Inject a Settings instance; never read
os.environ deep in the call tree.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
_YAML_FILES = ("settings.local.yaml", "settings.yaml")  # local (env-specific) wins over shared


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEG_", env_file=".env", extra="ignore")

    # --- secrets (.env) ---
    jira_token: str = ""  # Personal Access Token (Bearer)
    search_api_key: str = ""
    cosmos_key: str = ""
    idp_client_secret: str = ""
    idp_password: str = ""
    azure_client_secret: str = ""

    # --- environment non-secrets (config/settings.local.yaml) ---
    jira_base_url: str = ""
    search_endpoint: str = ""
    cosmos_endpoint: str = ""
    cosmos_database: str = ""
    llm_base_url: str = ""
    llm_app_id: str = ""
    idp_auth_url: str = ""
    idp_client_id: str = ""
    idp_user: str = ""
    azure_tenant_id: str = ""
    azure_client_id: str = ""

    # --- shared non-secrets (config/settings.yaml) ---
    # Jira
    jira_api_version: str = "2"
    jira_verify_ssl: bool = False
    jira_timeout_seconds: float = 30.0
    # Azure AI Search (one unified index; lane = entityType filter)
    search_index: str = "idp_teg_data"
    search_vector_field: str = "content_vector"
    search_semantic_config: str = "teg-semantic"
    search_api_version: str = "2024-07-01"  # needs >=2024-07-01 for the vector + complex schema
    # LLM (IDP OpenAI-compatible gateway)
    llm_completion_path: str = "/api/v1/chatcompletions"
    llm_model: str = "gpt-5-mini-idp"
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
    # Embeddings (same IDP gateway + auth as the LLM)
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1536  # must equal the index content_vector dimensions
    embedding_path: str = "/api/v1/embeddings"
    embedding_api_version: str = "2024-06-01"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]
        for name in _YAML_FILES:
            path = _CONFIG_DIR / name
            if path.exists():
                sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=path))
        sources.append(file_secret_settings)
        return tuple(sources)


def load_settings() -> Settings:
    return Settings()
