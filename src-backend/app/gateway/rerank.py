"""Configurable reranker: identity, HTTP endpoint or LLM pointwise."""
from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import httpx2
from pydantic import BaseModel

from ..schemas.config import RerankConfig
from ..services.config import ConfigService
from .llm_client import LLMClient


class _RerankScores(BaseModel):
    scores: list[float]


class Reranker:
    """Reranks documents using one of the configured modes."""

    def __init__(
        self,
        config_service: ConfigService,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.config_service = config_service
        self.http_client = http_client

    async def rerank(
        self,
        query: str,
        docs: Sequence[str],
        role: str = "rerank",
    ) -> list[dict]:
        config = self.config_service.load()
        rerank_config = getattr(config, role, None)
        if not isinstance(rerank_config, RerankConfig):
            raise ValueError(f"Unknown or unsupported role: {role}")

        if rerank_config.mode == "none":
            return [
                {"index": i, "text": doc, "score": 1.0}
                for i, doc in enumerate(docs)
            ]
        if rerank_config.mode == "endpoint":
            return await self._endpoint(query, docs, rerank_config)
        if rerank_config.mode == "llm":
            return await self._llm(query, docs)
        raise ValueError(f"Unknown rerank mode: {rerank_config.mode}")

    async def _endpoint(
        self,
        query: str,
        docs: Sequence[str],
        config: RerankConfig,
    ) -> list[dict]:
        if config.base_url is None:
            raise ValueError("Rerank endpoint is not configured")
        endpoint = str(config.base_url).rstrip("/")
        if not endpoint.endswith("/rerank"):
            endpoint = f"{endpoint}/rerank"
        headers: dict[str, str] = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key.get_secret_value()}"
        payload = {
            "model": config.model,
            "query": query,
            "documents": list(docs),
            "top_n": config.top_n,
        }
        try:
            if self.http_client is None:
                async with httpx2.AsyncClient(timeout=30.0) as owned_client:
                    response = await owned_client.post(
                        endpoint, json=payload, headers=headers
                    )
                    response.raise_for_status()
                    data = response.json()
            else:
                response = await self.http_client.post(
                    endpoint, json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - normalized for the caller
            raise ValueError(f"Rerank endpoint call failed: {exc}") from exc

        results = data.get("results", data.get("result", []))
        if not isinstance(results, list):
            results = []
        scored: list[dict[str, object]] = []
        for position, item in enumerate(results):
            if isinstance(item, dict):
                text = item.get("text") or item.get("document")
                if isinstance(text, str):
                    score_value = item.get("relevance_score", item.get("score", 0.0))
                    score = (
                        float(score_value)
                        if isinstance(score_value, (int, float))
                        else 0.0
                    )
                    index = item.get("index", position)
                    scored.append(
                        {"index": int(index) if isinstance(index, int) else position, "text": text, "score": score}
                    )
        if not scored:
            scored = [
                {"index": i, "text": doc, "score": 0.0}
                for i, doc in enumerate(docs)
            ]
        scored.sort(key=lambda item: cast(float, item["score"]), reverse=True)
        return scored[: config.top_n]

    async def _llm(self, query: str, docs: Sequence[str]) -> list[dict]:
        client = LLMClient(self.config_service, self.config_service.runtime_store)
        prompt = (
            "Score each document from 0 to 10 for relevance to the query. "
            "Return only JSON: {\"scores\": [<float>, ...]}.\n\n"
            f"Query: {query}\n\nDocuments:\n"
            + "\n".join(f"{i}. {doc}" for i, doc in enumerate(docs))
        )
        result = await client.chat(
            [{"role": "user", "content": prompt}],
            role="chat",
            response_model=_RerankScores,
            use_cache=False,
        )
        if not isinstance(result, _RerankScores):
            raise ValueError("Reranker received an unexpected response type")
        scores = list(result.scores)
        ranked = [
            {"index": i, "text": doc, "score": scores[i] if i < len(scores) else 0.0}
            for i, doc in enumerate(docs)
        ]
        ranked.sort(key=lambda item: cast(float, item["score"]), reverse=True)
        return ranked
