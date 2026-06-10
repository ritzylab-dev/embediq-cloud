# tests/test_envelope.py — every response matches the standard envelope
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

Headers = dict[str, str]


def test_success_envelope(client: TestClient, auth_headers: Headers) -> None:
    body = client.get("/api/v1/devices", headers=auth_headers).json()
    assert set(body.keys()) == {"data", "error"}
    assert body["error"] is None
    assert body["data"] is not None


def test_error_envelope(client: TestClient, auth_headers: Headers) -> None:
    body = client.get("/api/v1/devices/missing", headers=auth_headers).json()
    assert set(body.keys()) == {"data", "error"}
    assert body["data"] is None
    assert set(body["error"].keys()) == {"code", "message"}


def test_validation_error_is_400_envelope(client: TestClient, auth_headers: Headers) -> None:
    # Missing required field 'id' → standard 400 envelope (not FastAPI's 422 default).
    resp = client.post("/api/v1/devices", headers=auth_headers, json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"
