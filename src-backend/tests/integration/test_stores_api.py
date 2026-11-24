"""Integration tests for the storage status endpoint."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

TOKEN = "test-token"


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(str(tmp_path), auth_token=TOKEN))


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_stores_status_reports_schema_and_counts(tmp_path: Path) -> None:
    client = _client(tmp_path)

    resp = client.get("/api/stores/status", headers=_auth())

    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"]["vector"] in ("LanceVectorStore", "InMemoryVectorStore")
    assert body["backend"]["graph"] in ("LadybugGraphStore", "InMemoryGraphStore")
    assert body["vector"]["count"] == 0
    assert body["graph"]["node_count"] == 0
    assert body["schema_versions"]["sqlite"] == [1, 2]


def test_stores_status_requires_auth(tmp_path: Path) -> None:
    client = _client(tmp_path)

    assert client.get("/api/stores/status").status_code == 401
