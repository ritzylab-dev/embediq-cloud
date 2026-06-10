# tests/test_auth.py — single-admin login + JWT protection contract
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
import time

import jwt
from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PASS, ADMIN_USER


def test_login_success_returns_token(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert isinstance(body["data"]["token"], str)


def test_login_wrong_password_401(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_login_unknown_user_401(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "nobody", "password": ADMIN_PASS})
    assert resp.status_code == 401


def test_protected_route_without_token_401(client: TestClient) -> None:
    assert client.get("/api/v1/devices").status_code == 401


def test_protected_route_bad_token_401(client: TestClient) -> None:
    resp = client.get("/api/v1/devices", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_protected_route_expired_token_401(client: TestClient) -> None:
    expired = jwt.encode(
        {"sub": ADMIN_USER, "exp": int(time.time()) - 10}, "test-secret-key", algorithm="HS256"
    )
    resp = client.get("/api/v1/devices", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


def test_protected_route_valid_token_200(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/devices", headers=auth_headers).status_code == 200


def test_health_stays_public(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
