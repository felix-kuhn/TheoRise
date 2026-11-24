"""Deterministic fakes for tests: no network is ever touched."""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

import numpy as np
from pydantic import BaseModel

from app.services.config import KeyVault


class MemoryKeyVault(KeyVault):
    """In-memory vault for tests; never touches the OS keychain."""

    def __init__(self) -> None:
        super().__init__()
        self._memory: dict[str, str] = {}

    @property
    def available(self) -> bool:
        return False

    @property
    def warning(self) -> str | None:
        return None

    def get(self, role: str) -> str | None:
        return self._memory.get(role)

    def set(self, role: str, value: str) -> None:
        self._memory[role] = value

    def delete(self, role: str) -> None:
        self._memory.pop(role, None)

    def has(self, role: str) -> bool:
        return role in self._memory


class FakeLLM:
    """Rule-based chat fake; responses are registered per test."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        role: str,
        response_model: type[BaseModel] | None = None,
        stream: bool = False,
        job_id: str | None = None,
        use_cache: bool = True,
    ) -> BaseModel | str:
        self.calls.append(
            {
                "messages": list(messages),
                "role": role,
                "response_model": response_model,
                "job_id": job_id,
                "use_cache": use_cache,
            }
        )
        content = self.responses.pop(0) if self.responses else '{"ok": true}'
        if response_model is not None:
            return response_model.model_validate_json(content)
        return content


class FakeEmbedder:
    """Hash-based embeddings with fixed dimension 64."""

    def __init__(self, dimension: int = 64) -> None:
        self.dimension = dimension
        self.calls: list[dict[str, Any]] = []

    async def embed(
        self,
        texts: Sequence[str],
        kind: str = "document",
    ) -> np.ndarray:
        self.calls.append({"texts": list(texts), "kind": kind})
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            seed = int.from_bytes(digest[:8], "big")
            rng = np.random.default_rng(seed)
            vectors.append(rng.normal(size=self.dimension))
        matrix = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def fingerprint(self, role: str = "embedding") -> str:
        return hashlib.sha1(f"fake-{role}".encode()).hexdigest()


class FakeReranker:
    """Identity reranker used in contract tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def rerank(self, query: str, docs: Sequence[str]) -> list[dict]:
        self.calls.append({"query": query, "docs": list(docs)})
        return [
            {"index": i, "text": doc, "score": 1.0}
            for i, doc in enumerate(docs)
        ]


class FakeGateway:
    """Drop-in dependency override matching the Gateway facade."""

    def __init__(
        self,
        llm: FakeLLM | None = None,
        embedder: FakeEmbedder | None = None,
        reranker: FakeReranker | None = None,
        test_results: dict[str, dict] | None = None,
    ) -> None:
        self.llm = llm or FakeLLM()
        self.embedder = embedder or FakeEmbedder()
        self.reranker = reranker or FakeReranker()
        self.test_results = test_results or {}

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        role: str,
        response_model: type[BaseModel] | None = None,
        stream: bool = False,
        job_id: str | None = None,
        use_cache: bool = True,
    ) -> BaseModel | str:
        return await self.llm.chat(
            messages,
            role=role,
            response_model=response_model,
            stream=stream,
            job_id=job_id,
            use_cache=use_cache,
        )

    async def embed(self, texts: Sequence[str], kind: str = "document") -> np.ndarray:
        return await self.embedder.embed(texts, kind=kind)

    async def rerank(self, query: str, docs: Sequence[str]) -> list[dict]:
        return await self.reranker.rerank(query, docs)

    async def test_role(self, role: str) -> dict:
        if role in ("chat", "extraction", "linking"):
            await self.chat(
                [{"role": "user", "content": "Reply with {\"ok\": true}."}],
                role=role,
            )
        elif role == "embedding":
            await self.embed(["hello"], kind="query")
        elif role == "rerank":
            await self.rerank("hello", ["one", "two"])
        return self.test_results.get(
            role,
            {
                "role": role,
                "ok": True,
                "latency_ms": 3,
                "error": None,
                "detected": (
                    {"dimensions": self.embedder.dimension}
                    if role == "embedding"
                    else {}
                ),
            },
        )

    async def list_models(self, role: str) -> list[str]:
        return [f"fake-{role}-model"]

    def network_status(self) -> list[dict]:
        return [
            {
                "role": role,
                "base_url": "http://127.0.0.1:8000/v1",
                "host": "127.0.0.1",
                "local": True,
            }
            for role in ("chat", "extraction", "linking", "embedding", "rerank")
        ]
