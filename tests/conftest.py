# tests/conftest.py — shared fixtures for the API tests (temp DB + single-admin env)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from pathlib import Path

import bcrypt
import pytest
from fastapi.testclient import TestClient

ADMIN_USER = "admin"
ADMIN_PASS = "s3cret-pass"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    pass_hash = bcrypt.hashpw(ADMIN_PASS.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("ADMIN_USER", ADMIN_USER)
    monkeypatch.setenv("ADMIN_PASS_HASH", pass_hash)
    monkeypatch.setenv("JWT_SECRET", "test-secret-key")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRIDGE_ENABLED", "false")  # never touch a broker in tests

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A real, initialized temp SQLite DB for tests that exercise DB writes directly."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "bridge.db"))
    from app.db import init_db

    init_db()
    yield


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    token = resp.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
