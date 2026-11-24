"""Gateway contract tests using deterministic fakes and httpx2 mocks."""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import httpx2
import numpy as np
import pytest
from pydantic import BaseModel

from app.gateway.embeddings import Embedder
from app.gateway.gateway import Gateway
from app.gateway.llm_client import GatewayBudgetError, LLMClient
from app.gateway.rerank import Reranker
from app.services.config import ConfigService


class _Ok(BaseModel):
    ok: bool


def _chat_config() -> dict:
    return {
        "chat": {
            "base_url": "http://127.0.0.1:1/v1",
            "model": "chat-model",
            "api_key": "sk-test-secret",
        },
        "extraction": {
            "base_url": "http://127.0.0.1:1/v1",
            "model": "extract-model",
            "api_key": "sk-test-secret",
        },
    }


def _service(tmp_path: Path) -> ConfigService:
    service = ConfigService(tmp_path)
    service.save(_chat_config())
    return service


def _chat_response(content: str = '{"ok": true}') -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1,
            "model": "chat-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
    )


@pytest.mark.asyncio
async def test_chat_retries_on_transient_errors(tmp_path: Path, monkeypatch) -> None:
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx2.Response(429, json={"error": {"message": "rate limited"}})
        if len(calls) == 2:
            return httpx2.Response(500, json={"error": {"message": "boom"}})
        return _chat_response()

    service = _service(tmp_path)
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await LLMClient(service, service.runtime_store, client).chat(
            [{"role": "user", "content": "hello"}],
            role="chat",
            response_model=_Ok,
        )

    assert result == _Ok(ok=True)
    assert len(calls) == 3
    assert calls[0].headers["authorization"] == "Bearer sk-test-secret"


@pytest.mark.asyncio
async def test_structured_output_retries_with_validation_feedback(
    tmp_path: Path,
) -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        if len(calls) == 1:
            return _chat_response('{"ok": "not-a-boolean"}')
        return _chat_response()

    service = _service(tmp_path)
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await LLMClient(service, service.runtime_store, client).chat(
            [{"role": "user", "content": "hello"}],
            role="chat",
            response_model=_Ok,
        )

    assert result == _Ok(ok=True)
    assert len(calls) == 2
    last_body = json.loads(calls[1].content.decode("utf-8"))
    assert "could not be parsed" in last_body["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_json_schema_detection_falls_back_on_unsupported(tmp_path: Path) -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx2.Response(400, json={"error": {"message": "unsupported"}})
        return _chat_response()

    service = _service(tmp_path)
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await LLMClient(service, service.runtime_store, client).chat(
            [{"role": "user", "content": "hello"}],
            role="chat",
            response_model=_Ok,
        )

    assert result == _Ok(ok=True)
    assert service.load().chat.supports_json_schema is False
    assert len(calls) == 2


def test_api_key_survives_role_detection_updates(tmp_path: Path) -> None:
    service = _service(tmp_path)

    service.set_role_detection("chat", supports_json_schema=False)
    config = service.load()

    assert config.chat.supports_json_schema is False
    assert config.chat.api_key is not None
    assert config.chat.api_key.get_secret_value() == "sk-test-secret"


@pytest.mark.asyncio
async def test_chat_cache_reuses_stored_response(tmp_path: Path) -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return _chat_response()

    service = _service(tmp_path)
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        llm = LLMClient(service, service.runtime_store, client)
        first = await llm.chat(
            [{"role": "user", "content": "hello"}],
            role="extraction",
            response_model=_Ok,
        )
        second = await llm.chat(
            [{"role": "user", "content": "hello"}],
            role="extraction",
            response_model=_Ok,
        )

    assert first == second == _Ok(ok=True)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_token_budget_blocks_over_budget_job(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.runtime_store.record_usage(
        job_id="job-1",
        role="chat",
        prompt_tokens=10,
        completion_tokens=0,
        total_tokens=10,
        model="chat-model",
    )
    service.save({"token_budget_per_job": 10})

    with pytest.raises(GatewayBudgetError):
        await LLMClient(service, service.runtime_store).chat(
            [{"role": "user", "content": "hello"}],
            role="chat",
            job_id="job-1",
        )


@pytest.mark.asyncio
async def test_embedder_decodes_base64_vectors(tmp_path: Path) -> None:
    vector = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    encoded = base64.b64encode(vector.tobytes()).decode("ascii")

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": "embed-model",
                "data": [{"object": "embedding", "index": 0, "embedding": encoded}],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    service = _service(tmp_path)
    service.save(
        {"embedding": {"base_url": "http://127.0.0.1:1/v1", "model": "embed-model"}}
    )
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await Embedder(service, client).embed(["hello"], kind="query")

    assert result.shape == (1, 4)
    assert np.allclose(result[0], [1.0, 0.0, 0.0, 0.0])


@pytest.mark.asyncio
async def test_embedder_applies_prefixes_and_batches(tmp_path: Path) -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        payload = json.loads(request.content.decode("utf-8"))
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": "embed-model",
                "data": [
                    {"object": "embedding", "index": i, "embedding": [1.0, 0.0]}
                    for i in range(len(payload["input"]))
                ],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    service = _service(tmp_path)
    service.save(
        {
            "embedding": {
                "base_url": "http://127.0.0.1:1/v1",
                "model": "embed-model",
                "query_prefix": "q:",
                "document_prefix": "d:",
                "batch_size": 2,
            }
        }
    )
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        await Embedder(service, client).embed(["a", "b", "c", "d"], kind="query")

    assert len(requests) == 2
    first = json.loads(requests[0].content.decode("utf-8"))
    second = json.loads(requests[1].content.decode("utf-8"))
    assert first["input"] == ["q:a", "q:b"]
    assert second["input"] == ["q:c", "q:d"]


@pytest.mark.asyncio
async def test_gateway_detects_embedding_dimensions(tmp_path: Path) -> None:
    vector = np.asarray([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
    encoded = base64.b64encode(vector.tobytes()).decode("ascii")

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/embeddings"):
            return httpx2.Response(
                200,
                json={
                    "object": "list",
                    "model": "embed-model",
                    "data": [{"object": "embedding", "index": 0, "embedding": encoded}],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )
        return httpx2.Response(
            200,
            json={"object": "list", "data": [{"id": "embed-model"}]},
        )

    service = _service(tmp_path)
    service.save(
        {"embedding": {"base_url": "http://127.0.0.1:1/v1", "model": "embed-model"}}
    )
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await Gateway(service, client).test_role("embedding")

    assert result["ok"] is True
    assert result["detected"]["dimensions"] == 4
    assert service.load().embedding.dimensions == 4


@pytest.mark.asyncio
async def test_reranker_endpoint_parses_and_sorts_results(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/rerank")
        return httpx2.Response(
            200,
            json={
                "results": [
                    {"index": 0, "text": "first", "relevance_score": 0.2},
                    {"index": 1, "text": "second", "relevance_score": 0.9},
                ]
            },
        )

    service = _service(tmp_path)
    service.save(
        {
            "rerank": {
                "mode": "endpoint",
                "base_url": "http://127.0.0.1:1/v1",
                "model": "rerank-model",
                "api_key": "sk-test-secret",
                "top_n": 1,
            }
        }
    )
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await Reranker(service, client).rerank("query", ["first", "second"])

    assert result == [{"index": 1, "text": "second", "score": 0.9}]


@pytest.mark.asyncio
async def test_streaming_accumulates_chunks(tmp_path: Path, monkeypatch) -> None:
    class _Stream:
        def __init__(self, chunks: list[str]) -> None:
            self._chunks = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self) -> SimpleNamespace:
            try:
                content = next(self._chunks)
            except StopIteration:
                raise StopAsyncIteration from None
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(delta=SimpleNamespace(content=content))
                ]
            )

    async def fake_create(**_params):
        return _Stream(["Hello", " world"])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    service = _service(tmp_path)
    llm = LLMClient(service, service.runtime_store)
    monkeypatch.setattr(llm, "_client", lambda _role_config: fake_client)

    result = await llm.chat(
        [{"role": "user", "content": "hello"}],
        role="chat",
        stream=True,
    )

    assert result == "Hello world"
