# tests/test_registry.py — devices CRUD + cascade contract
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

Headers = dict[str, str]


def test_create_device_201(client: TestClient, auth_headers: Headers) -> None:
    resp = client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-1"})
    assert resp.status_code == 201
    assert resp.json()["data"]["id"] == "dev-1"


def test_create_duplicate_409(client: TestClient, auth_headers: Headers) -> None:
    client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-1"})
    resp = client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-1"})
    assert resp.status_code == 409


def test_list_devices(client: TestClient, auth_headers: Headers) -> None:
    client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-1"})
    client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-2"})
    resp = client.get("/api/v1/devices", headers=auth_headers)
    assert resp.status_code == 200
    ids = {d["id"] for d in resp.json()["data"]}
    assert {"dev-1", "dev-2"} <= ids


def test_get_device_200_and_404(client: TestClient, auth_headers: Headers) -> None:
    client.post(
        "/api/v1/devices",
        headers=auth_headers,
        json={"id": "dev-1", "attributes": {"site": "lab"}},
    )
    ok = client.get("/api/v1/devices/dev-1", headers=auth_headers)
    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data["attributes"] == {"site": "lab"}
    assert data["state"]["online"] is False
    assert client.get("/api/v1/devices/missing", headers=auth_headers).status_code == 404


def test_patch_device(client: TestClient, auth_headers: Headers) -> None:
    client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-1"})
    resp = client.patch("/api/v1/devices/dev-1", headers=auth_headers, json={"group_id": "fleet-a"})
    assert resp.status_code == 200
    assert (
        client.get("/api/v1/devices/dev-1", headers=auth_headers).json()["data"]["group_id"]
        == "fleet-a"
    )
    assert client.patch("/api/v1/devices/missing", headers=auth_headers, json={}).status_code == 404


def test_delete_device_cascade(client: TestClient, auth_headers: Headers) -> None:
    client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-1"})
    assert client.delete("/api/v1/devices/dev-1", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/devices/dev-1", headers=auth_headers).status_code == 404
    assert client.delete("/api/v1/devices/dev-1", headers=auth_headers).status_code == 404
