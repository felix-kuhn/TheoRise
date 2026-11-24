"""Contract tests for the runtime config API."""
from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

from tests.fakes import FakeGateway


def _config_payload(api_key: str | None = "sk-test-secret") -> dict:
    return {
        "chat": {
            "base_url": "http://127.0.0.1:8000/v1",
            "model": "fake-chat",
            "api_key": api_key,
            "system_instructions": "Answer concisely.",
            "temperature": 0.1,
        },
        "extraction": {
            "base_url": "http://127.0.0.1:8000/v1",
            "model": "fake-extraction",
            "api_key": api_key,
        },
        "linking": {
            "base_url": "http://127.0.0.1:8000/v1",
            "model": "fake-linking",
            "api_key": api_key,
        },
        "embedding": {
            "base_url": "http://127.0.0.1:8000/v1",
            "model": "fake-embedding",
            "api_key": api_key,
            "batch_size": 4,
        },
        "rerank": {
            "mode": "none",
            "base_url": "http://127.0.0.1:8000/v1",
            "model": "fake-rerank",
            "api_key": api_key,
            "top_n": 3,
        },
        "concurrency": 2,
        "token_budget_per_job": 5000,
    }


def test_get_config_masks_api_keys(config_client: TestClient, auth_headers: dict) -> None:
    response = config_client.get("/api/config", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert "sk-test-secret" not in json.dumps(body)
    assert body["chat"]["api_key_set"] is False
    assert body["embedding"]["batch_size"] == 32
    assert body["concurrency"] == 4
    assert body["keychain"]["available"] is False


def test_put_config_roundtrip_keep_and_clear(
    config_client: TestClient,
    auth_headers: dict,
) -> None:
    response = config_client.put(
        "/api/config",
        headers=auth_headers,
        json=_config_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert "sk-test-secret" not in json.dumps(body)
    assert body["chat"]["api_key_set"] is True
    assert body["chat"]["model"] == "fake-chat"

    kept = _config_payload()
    for role in ("chat", "extraction", "linking", "embedding", "rerank"):
        kept[role].pop("api_key", None)
    response = config_client.put("/api/config", headers=auth_headers, json=kept)
    assert response.json()["chat"]["api_key_set"] is True

    cleared = _config_payload()
    for role in ("chat", "extraction", "linking", "embedding", "rerank"):
        cleared[role]["api_key"] = None
    response = config_client.put("/api/config", headers=auth_headers, json=cleared)
    body = response.json()
    assert body["chat"]["api_key_set"] is False
    assert body["embedding"]["api_key_set"] is False


def test_empty_string_api_key_clears_existing(
    config_client: TestClient,
    auth_headers: dict,
) -> None:
    response = config_client.put(
        "/api/config",
        headers=auth_headers,
        json=_config_payload(),
    )
    assert response.json()["chat"]["api_key_set"] is True

    payload = _config_payload(api_key="")
    response = config_client.put("/api/config", headers=auth_headers, json=payload)
    assert response.json()["chat"]["api_key_set"] is False


def test_put_config_validation_errors_are_uniform(
    config_client: TestClient,
    auth_headers: dict,
) -> None:
    response = config_client.put(
        "/api/config",
        headers=auth_headers,
        json={"concurrency": "many"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    assert body["details"]["errors"]


def test_config_test_single_role(
    config_client: TestClient,
    auth_headers: dict,
    fake_gateway: FakeGateway,
) -> None:
    response = config_client.post(
        "/api/config/test",
        headers=auth_headers,
        json={"role": "chat"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "chat"
    assert body["ok"] is True
    assert body["latency_ms"] >= 0
    assert fake_gateway.llm.calls


def test_config_test_all_roles(
    config_client: TestClient,
    auth_headers: dict,
) -> None:
    response = config_client.post("/api/config/test", headers=auth_headers, json={})
    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["role"] for item in results] == [
        "chat",
        "extraction",
        "linking",
        "embedding",
        "rerank",
    ]
    assert all(item["ok"] for item in results)


def test_config_models_and_network_status(
    config_client: TestClient,
    auth_headers: dict,
) -> None:
    models = config_client.get(
        "/api/config/models",
        headers=auth_headers,
        params={"role": "chat"},
    )
    assert models.status_code == 200
    assert models.json()["models"] == ["fake-chat-model"]

    status = config_client.get("/api/config/network-status", headers=auth_headers)
    assert status.status_code == 200
    assert all(item["local"] for item in status.json()["roles"])


def test_config_routes_require_auth(config_client: TestClient) -> None:
    assert config_client.get("/api/config").status_code == 401
    assert config_client.post("/api/config/test", json={}).status_code == 401


def test_chat_routes_through_backend_gateway(
    config_client: TestClient,
    auth_headers: dict,
    fake_gateway: FakeGateway,
) -> None:
    response = config_client.post(
        "/api/chat",
        headers=auth_headers,
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200
    assert response.json() == {"content": '{"ok": true}'}
    assert fake_gateway.llm.calls[-1]["messages"][0]["content"] == "hello"


def test_api_keys_never_reach_logs(
    config_client: TestClient,
    auth_headers: dict,
    caplog,
) -> None:
    with caplog.at_level(logging.INFO):
        response = config_client.put(
            "/api/config",
            headers=auth_headers,
            json=_config_payload(),
        )
    assert response.status_code == 200
    assert "sk-test-secret" not in caplog.text
