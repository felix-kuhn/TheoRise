"""OpenAI-compatible chat client with retries and structured output."""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
from collections.abc import Sequence
from typing import Any

import httpx2
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
    UnprocessableEntityError,
)
from pydantic import BaseModel, ValidationError

from ..schemas.config import AppConfig, ModelRoleConfig
from ..services.config import ConfigService
from ..stores.sqlite.runtime_store import RuntimeStore


class GatewayError(RuntimeError):
    """Raised when a provider call cannot complete."""


class GatewayConfigError(GatewayError):
    """Raised when a role is not configured yet."""


class GatewayBudgetError(GatewayError):
    """Raised when a job exceeds its configured token budget."""


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, APIStatusError):
        return f"HTTP {exc.status_code}: {exc.message}"
    text = str(exc)
    return text[:500] or exc.__class__.__name__


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (408, 429) or (
        isinstance(status, int) and status >= 500
    ):
        return True
    if isinstance(exc, (RateLimitError, InternalServerError)):
        return True
    return isinstance(
        exc,
        (
            httpx2.TimeoutException,
            httpx2.TransportError,
            APITimeoutError,
            APIConnectionError,
        ),
    )


def _is_unsupported(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return status in (400, 404, 422) or isinstance(
        exc,
        (
            BadRequestError,
            NotFoundError,
            UnprocessableEntityError,
            httpx2.HTTPStatusError,
        ),
    )


def _estimate_tokens(messages: Sequence[dict[str, str]]) -> int:
    return max(1, sum(len(message.get("content", "")) for message in messages) // 4)


def _prepare_messages(
    messages: Sequence[dict[str, str]],
    system_instructions: str,
) -> list[dict[str, str]]:
    prepared: list[dict[str, str]] = []
    if system_instructions:
        prepared.append({"role": "system", "content": system_instructions})
    for message in messages:
        role = message.get("role", "user")
        if role == "system" and prepared and prepared[-1]["role"] == "system":
            prepared[-1]["content"] = (
                f"{prepared[-1]['content']}\n\n{message.get('content', '')}"
            ).strip()
            continue
        prepared.append({"role": role, "content": message.get("content", "")})
    return prepared


def _extract_json(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


class LLMClient:
    """Chat completions with retries, JSON validation and usage accounting."""

    PROMPT_VERSION = "inc-02"

    def __init__(
        self,
        config_service: ConfigService,
        runtime_store: RuntimeStore,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.config_service = config_service
        self.runtime_store = runtime_store
        self.http_client = http_client

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        role: str,
        response_model: type[BaseModel] | None = None,
        stream: bool = False,
        job_id: str | None = None,
        use_cache: bool = True,
    ) -> BaseModel | str:
        config = self.config_service.load()
        role_config = getattr(config, role, None)
        if not isinstance(role_config, ModelRoleConfig):
            raise GatewayConfigError(f"Unknown or unsupported role: {role}")
        if not role_config.model:
            raise GatewayConfigError(f"Model for role '{role}' is not configured")

        prepared = _prepare_messages(messages, role_config.system_instructions)
        self._check_budget(config, prepared, job_id)

        cache_key = self._cache_key(role, role_config, prepared, response_model)
        if use_cache and role in ("extraction", "linking") and response_model:
            cached = self.runtime_store.cache_get(cache_key)
            if cached is not None:
                return self._parse_cached(cached, response_model)

        supports_json_schema = role_config.supports_json_schema
        last_error: Exception | None = None

        for attempt in range(3):
            use_json_schema = (
                supports_json_schema is True
                or (supports_json_schema is None and attempt == 0 and response_model is not None)
            )
            try:
                content = await self._call_once(
                    config,
                    role_config,
                    prepared,
                    role,
                    response_model,
                    stream,
                    job_id,
                    use_json_schema,
                )
                if response_model is None:
                    return content
                try:
                    result = response_model.model_validate_json(_extract_json(content))
                    if supports_json_schema is None:
                        self.config_service.set_role_detection(
                            role, supports_json_schema=use_json_schema
                        )
                    if use_cache and role in ("extraction", "linking"):
                        self.runtime_store.cache_set(cache_key, content)
                    return result
                except ValidationError as exc:
                    if attempt >= 2:
                        raise GatewayError(
                            f"Provider returned invalid JSON for role '{role}': {exc}"
                        ) from exc
                    prepared = [
                        *prepared,
                        {
                            "role": "user",
                            "content": (
                                "Your previous response could not be parsed. "
                                f"Return only valid JSON matching the schema. Error: {exc}"
                            ),
                        },
                    ]
                    continue
            except Exception as exc:  # noqa: BLE001 - provider errors are normalized
                if supports_json_schema is None and _is_unsupported(exc):
                    supports_json_schema = False
                    self.config_service.set_role_detection(
                        role, supports_json_schema=False
                    )
                    last_error = exc
                    continue
                if _is_retryable(exc) and attempt < 2:
                    await asyncio.sleep(0.2 * (2**attempt) + random.uniform(0, 0.05))
                    last_error = exc
                    continue
                raise GatewayError(f"Chat call failed for role '{role}': {_safe_error(exc)}") from exc

        raise GatewayError(
            f"Chat call failed for role '{role}': {_safe_error(last_error) if last_error else 'unknown error'}"
        )

    async def _call_once(
        self,
        config: AppConfig,
        role_config: ModelRoleConfig,
        messages: list[dict[str, str]],
        role: str,
        response_model: type[BaseModel] | None,
        stream: bool,
        job_id: str | None,
        use_json_schema: bool,
    ) -> str:
        client = self._client(role_config)
        params: dict[str, Any] = {
            "model": role_config.model,
            "messages": messages,
            "temperature": role_config.temperature,
        }
        if role_config.max_tokens is not None:
            params["max_tokens"] = role_config.max_tokens
        if stream:
            params["stream"] = True
        if response_model is not None:
            if use_json_schema:
                params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": response_model.model_json_schema(),
                        "strict": True,
                    },
                }
            else:
                params["response_format"] = {"type": "json_object"}
        params.update(role_config.extra_body)

        completion = await client.chat.completions.create(**params)
        if stream:
            chunks: list[str] = []
            async for chunk in completion:
                if chunk.choices:
                    delta = getattr(chunk.choices[0].delta, "content", None)
                    if delta:
                        chunks.append(delta)
            return "".join(chunks)
        usage = getattr(completion, "usage", None)
        if usage is not None:
            self.runtime_store.record_usage(
                job_id=job_id or "anonymous",
                role=role,
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
                model=role_config.model,
            )
        content = getattr(completion.choices[0].message, "content", None) if completion.choices else None
        return content or ""

    def _client(self, role_config: ModelRoleConfig) -> AsyncOpenAI:
        api_key = role_config.api_key.get_secret_value() if role_config.api_key else "none"
        return AsyncOpenAI(
            api_key=api_key,
            base_url=str(role_config.base_url).rstrip("/"),
            timeout=role_config.timeout_s,
            max_retries=0,
            default_headers=role_config.extra_headers or None,
            http_client=self.http_client,
        )

    def _check_budget(
        self,
        config: AppConfig,
        messages: Sequence[dict[str, str]],
        job_id: str | None,
    ) -> None:
        budget = config.token_budget_per_job
        if budget is None or not job_id:
            return
        total = self.runtime_store.usage_total(job_id)
        if total >= budget:
            raise GatewayBudgetError(
                f"Token budget of {budget} tokens exceeded for job {job_id}"
            )
        if total + _estimate_tokens(messages) > budget:
            raise GatewayBudgetError(
                f"Token budget of {budget} tokens exceeded for job {job_id}"
            )

    def _cache_key(
        self,
        role: str,
        role_config: ModelRoleConfig,
        messages: Sequence[dict[str, str]],
        response_model: type[BaseModel] | None,
    ) -> str:
        schema = response_model.model_json_schema() if response_model else None
        payload = json.dumps(
            {
                "role": role,
                "model": role_config.model,
                "base_url": str(role_config.base_url),
                "prompt_version": self.PROMPT_VERSION,
                "messages": messages,
                "schema": schema,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _parse_cached(self, cached: str, response_model: type[BaseModel]) -> BaseModel:
        try:
            return response_model.model_validate_json(_extract_json(cached))
        except ValidationError as exc:
            raise GatewayError("Cached provider response is invalid") from exc
