"""IDP LLM gateway client (async, structured output).

The gateway is OpenAI-compatible with two POC-confirmed quirks: custom IDP bearer
auth (see idp_auth) and a response that wraps the single result under "choice"
instead of "choices". Guardrails are enforced gateway-side, so there is no prompt
sanitization here. The output structure is requested as a json_schema built from the
caller's pydantic model and re-validated locally.
"""

from __future__ import annotations

import logging
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel

from teg.config.settings import Settings
from teg.integrations.llm.idp_auth import IDPCustomAuth

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class IdpLLMClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        model: str,
        completion_path: str = "/chat/completions",
        api_version: str = "2024-04-01-preview",
        reasoning_effort: str | None = None,
    ) -> None:
        self._http = http_client
        self._model = model
        self._completion_path = completion_path
        self._api_version = api_version
        self._reasoning_effort = reasoning_effort or None

    async def complete(self, *, system: str, user: str, schema: type[ModelT]) -> ModelT:
        body: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(by_alias=True),
                },
            },
            "api_version": self._api_version,
        }
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort

        started = time.perf_counter()
        response = await self._http.post(self._completion_path, json=body)
        response.raise_for_status()
        elapsed = time.perf_counter() - started

        content = _extract_content(response.json())
        logger.info("LLM %s -> %s in %.2fs", self._model, schema.__name__, elapsed)
        try:
            return schema.model_validate_json(content)
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"LLM output failed {schema.__name__} validation: {exc}") from exc


def _extract_content(payload: dict) -> str:
    if payload.get("error"):
        raise LLMError(str(payload["error"]))
    choice = payload.get("choice")  # IDP gateway quirk: single "choice"
    if choice is None:
        choices = payload.get("choices") or []
        choice = choices[0] if choices else {}
    content = (choice.get("message") or {}).get("content")
    if not content:
        raise LLMError("LLM returned no content")
    return content


def build_llm_client(settings: Settings) -> IdpLLMClient:
    auth = IDPCustomAuth(
        app_id=settings.llm_app_id,
        auth_url=settings.idp_auth_url,
        client_id=settings.idp_client_id,
        client_secret=settings.idp_client_secret,
        user=settings.idp_user,
        password=settings.idp_password,
    )
    http_client = httpx.AsyncClient(
        base_url=settings.llm_base_url,
        auth=auth,
        timeout=settings.llm_timeout_seconds,
        verify=settings.llm_verify_ssl,
    )
    return IdpLLMClient(
        http_client,
        model=settings.llm_model,
        completion_path=settings.llm_completion_path,
        api_version=settings.llm_api_version,
        reasoning_effort=settings.llm_reasoning_effort or None,
    )
