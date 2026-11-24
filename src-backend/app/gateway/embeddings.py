"""Embedding client with prefixes, batching and L2 normalization."""
from __future__ import annotations

import base64
import hashlib
from collections.abc import Sequence
from typing import Any

import httpx2
import numpy as np
from openai import AsyncOpenAI

from ..schemas.config import EmbeddingConfig
from ..services.config import ConfigService
from .llm_client import GatewayConfigError, GatewayError


def _decode_embedding(value: Any) -> list[float]:
    if isinstance(value, str):
        try:
            raw = base64.b64decode(value)
        except Exception as exc:  # noqa: BLE001 - normalized for the caller
            raise GatewayError("Embedding response contained invalid base64 data") from exc
        return np.frombuffer(raw, dtype=np.float32).tolist()
    if isinstance(value, (list, tuple)):
        return [float(item) for item in value]
    raise GatewayError("Embedding response contained an unsupported vector type")


def _chunks(items: Sequence[str], size: int) -> list[list[str]]:
    size = max(1, size)
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


class Embedder:
    """OpenAI-compatible embeddings with deterministic ordering."""

    def __init__(
        self,
        config_service: ConfigService,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.config_service = config_service
        self.http_client = http_client

    async def embed(
        self,
        texts: Sequence[str],
        kind: str = "document",
        role: str = "embedding",
    ) -> np.ndarray:
        config = self.config_service.load()
        embedding_config = getattr(config, role, None)
        if not isinstance(embedding_config, EmbeddingConfig):
            raise GatewayConfigError(f"Unknown or unsupported role: {role}")
        if not embedding_config.model:
            raise GatewayConfigError(f"Model for role '{role}' is not configured")

        prefix = (
            embedding_config.document_prefix
            if kind == "document"
            else embedding_config.query_prefix
        )
        inputs = [f"{prefix}{text}" for text in texts]
        if not inputs:
            return np.zeros((0, embedding_config.dimensions or 0), dtype=np.float32)

        client = self._client(embedding_config)
        vectors: list[list[float]] = []
        try:
            for batch in _chunks(inputs, embedding_config.batch_size):
                response = await client.embeddings.create(
                    model=embedding_config.model,
                    input=batch,
                )
                ordered = sorted(response.data, key=lambda item: getattr(item, "index", 0))
                vectors.extend([_decode_embedding(item.embedding) for item in ordered])
        except Exception as exc:  # noqa: BLE001 - normalized for the caller
            raise GatewayError(f"Embedding call failed for role '{role}': {exc}") from exc

        matrix = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def fingerprint(self, role: str = "embedding") -> str:
        config = self.config_service.load()
        embedding_config = getattr(config, role)
        raw = (
            f"{embedding_config.base_url}|{embedding_config.model}|"
            f"{embedding_config.dimensions}|{embedding_config.query_prefix}|"
            f"{embedding_config.document_prefix}"
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _client(self, embedding_config: EmbeddingConfig) -> AsyncOpenAI:
        api_key = embedding_config.api_key.get_secret_value() if embedding_config.api_key else "none"
        return AsyncOpenAI(
            api_key=api_key,
            base_url=str(embedding_config.base_url).rstrip("/"),
            timeout=embedding_config.timeout_s,
            max_retries=0,
            default_headers=embedding_config.extra_headers or None,
            http_client=self.http_client,
        )
