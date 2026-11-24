"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import get_gateway
from app.main import create_app
from tests.fakes import FakeGateway, MemoryKeyVault

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
TEST_TOKEN = "test-token"


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture
def fake_gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def config_client(tmp_path: Path, fake_gateway: FakeGateway) -> TestClient:
    app = create_app(str(tmp_path), auth_token=TEST_TOKEN)
    app.state.ctx.config_service.vault = MemoryKeyVault()
    app.dependency_overrides[get_gateway] = lambda: fake_gateway
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}
