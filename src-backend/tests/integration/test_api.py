"""Integration tests for the FastAPI application."""
from __future__ import annotations

import json
import select
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.pipelines.wiki import scraper

SAMPLE_HTML = "<h1>Activity Theory</h1><p>Sample content</p>"
TIMESTAMP = "20261028T161730Z"
TOKEN = "test-token"


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(str(tmp_path), auth_token=TOKEN))


def _write_theory(data_dir: Path) -> Path:
    theories_dir = data_dir / "theories"
    theories_dir.mkdir(parents=True, exist_ok=True)
    path = theories_dir / f"Activity_Theory_{TIMESTAMP}.html"
    path.write_text(SAMPLE_HTML, encoding="utf-8")
    return path


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/v1/theories/jobs/{job_id}", headers=_auth())
        body = resp.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish")


def test_health(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/health", headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data_dir"] == str(tmp_path)
    assert body["files"] == 0
    assert body["version"] == "0.1.0"


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_list_and_get_theory(tmp_path):
    _write_theory(tmp_path)
    client = _client(tmp_path)

    listing = client.get("/v1/theories", headers=_auth())
    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 1
    theory = body["theories"][0]
    assert theory["slug"] == "Activity_Theory"
    assert theory["title"] == "Activity Theory"
    assert theory["tokens"] > 0

    detail = client.get("/v1/theories/Activity_Theory", headers=_auth())
    assert detail.status_code == 200
    assert detail.json()["content"] == SAMPLE_HTML


def test_missing_theory_returns_uniform_error(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/v1/theories/does_not_exist", headers=_auth())
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"
    assert resp.json()["message"] == "not_found"
    assert resp.json()["details"] == {"slug": "does_not_exist"}


def test_hydrate_and_job_status(tmp_path, monkeypatch):
    def fake_hydration(cfg, theories_dir, job):
        job.update(stage="scrape", progress=0.5, detail="fake")
        theories_dir.mkdir(parents=True, exist_ok=True)
        path = theories_dir / f"Fake_Theory_{TIMESTAMP}.html"
        path.write_text("<h1>Fake</h1>", encoding="utf-8")
        return {
            "scraped": 1,
            "errors": [],
            "files": [{"slug": "Fake_Theory", "file": path.name}],
            "timestamp": TIMESTAMP,
        }

    monkeypatch.setattr(scraper, "run_hydration", fake_hydration)
    client = _client(tmp_path)

    resp = client.post("/v1/theories/hydrate", headers=_auth())
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    body = _wait_for_job(client, job_id)
    assert body["status"] == "done"
    assert body["result"]["scraped"] == 1
    assert client.get("/v1/theories/Fake_Theory", headers=_auth()).status_code == 200


def test_auth_required(tmp_path):
    client = _client(tmp_path)

    assert client.get("/health").status_code == 401
    assert client.get("/api/health").status_code == 401
    body = client.get("/health").json()
    assert body["code"] == "unauthorized"

    ok = client.get("/health", headers=_auth())
    assert ok.status_code == 200


def test_cli_prints_port_json(tmp_path):
    backend_root = Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app",
            "--port",
            "0",
            "--token",
            TOKEN,
            "--data-dir",
            str(tmp_path / "backend-data"),
        ],
        cwd=backend_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = ""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not line:
            ready, _, _ = select.select([proc.stdout], [], [], 0.1)
            if ready:
                line = proc.stdout.readline().strip()

        assert line, "backend did not print its port line"
        payload = json.loads(line)
        assert isinstance(payload["port"], int)
        assert 0 < payload["port"] < 65536

        request = urllib.request.Request(
            f"http://127.0.0.1:{payload['port']}/api/health",
            headers=_auth(),
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["status"] == "ok"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
