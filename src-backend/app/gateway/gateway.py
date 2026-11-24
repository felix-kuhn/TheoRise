"""Facade wiring the gateway clients to the runtime config."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from typing import Any

import httpx2
from openai import AsyncOpenAI
from pydantic import BaseModel

from ..schemas.config import ROLE_NAMES, RerankConfig
from ..services.config import ConfigService
from .capabilities import network_status
from .embeddings import Embedder
from .llm_client import GatewayError, LLMClient
from .rerank import Reranker


class _TinyResponse(BaseModel):
    ok: bool


class Gateway:
    """Shared gateway facade with concurrency limiting and probes."""

    def __init__(
        self,
        config_service: ConfigService,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.config_service = config_service
        self.http_client = http_client
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_loop: asyncio.AbstractEventLoop | None = None

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
        client = LLMClient(self.config_service, self.config_service.runtime_store, self.http_client)
        async with self._get_semaphore(config.concurrency):
            return await client.chat(
                messages,
                role=role,
                response_model=response_model,
                stream=stream,
                job_id=job_id,
                use_cache=use_cache,
            )

    async def embed(self, texts: Sequence[str], kind: str = "document") -> Any:
        config = self.config_service.load()
        client = Embedder(self.config_service, self.http_client)
        async with self._get_semaphore(config.concurrency):
            return await client.embed(texts, kind=kind)

    async def rerank(self, query: str, docs: Sequence[str]) -> list[dict]:
        config = self.config_service.load()
        client = Reranker(self.config_service, self.http_client)
        async with self._get_semaphore(config.concurrency):
            return await client.rerank(query, docs)

    async def test_role(self, role: str) -> dict:
        if role not in ROLE_NAMES:
            raise ValueError(f"Unknown role: {role}")
        started = time.perf_counter()
        detected: dict[str, Any] = {}
        error: str | None = None
        try:
            if role in ("chat", "extraction", "linking"):
                await self.chat(
                    [{"role": "user", "content": "Reply with {\"ok\": true}."}],
                    role=role,
                    response_model=_TinyResponse,
                    use_cache=False,
                )
                config = self.config_service.load()
                detected["supports_json_schema"] = getattr(config, role).supports_json_schema
            elif role == "embedding":
                vectors = await self.embed(["hello"], kind="query")
                dimensions = int(vectors.shape[1])
                detected["dimensions"] = dimensions
                self.config_service.set_role_detection(role, dimensions=dimensions)
            elif role == "rerank":
                await self.rerank("hello", ["one", "two"])
                detected["mode"] = self.config_service.load().rerank.mode
            if role == "rerank" and self.config_service.load().rerank.mode == "none":
                detected["models_listed"] = []
            else:
                models = await self.list_models(role)
                detected["models_listed"] = models
            ok = True
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            ok = False
            error = str(exc)[:500]
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "role": role,
            "ok": ok,
            "latency_ms": latency_ms,
            "error": error,
            "detected": detected,
        }

    async def list_models(self, role: str) -> list[str]:
        config = self.config_service.load()
        role_config = getattr(config, role)
        if role == "rerank":
            if not isinstance(role_config, RerankConfig) or role_config.base_url is None:
                raise GatewayError("Rerank endpoint is not configured")
        if getattr(role_config, "base_url", None) is None:
            raise GatewayError(f"Base URL for role '{role}' is not configured")
        api_key = getattr(role_config, "api_key", None)
        client = AsyncOpenAI(
            api_key=api_key.get_secret_value() if api_key else "none",
            base_url=str(role_config.base_url).rstrip("/"),
            timeout=30.0,
            max_retries=0,
            http_client=self.http_client,
        )
        response = await client.models.list()
        return [model.id for model in response.data]

    def network_status(self) -> list[dict]:
        return network_status(self.config_service.load())

    def _get_semaphore(self, concurrency: int) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._semaphore is None or self._semaphore_loop is not loop:
            self._semaphore = asyncio.Semaphore(concurrency)
            self._semaphore_loop = loop
        return self._semaphore
