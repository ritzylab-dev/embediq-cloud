# tests/test_groups.py — groups CRUD + default-group invariants
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

Headers = dict[str, str]


def test_create_and_list_groups(client: TestClient, auth_headers: Headers) -> None:
    assert (
        client.post("/api/v1/groups", headers=auth_headers, json={"id": "fleet-a"}).status_code
        == 201
    )
    resp = client.get("/api/v1/groups", headers=auth_headers)
    assert resp.status_code == 200
    ids = {g["id"] for g in resp.json()["data"]}
    assert {"default", "fleet-a"} <= ids


def test_create_duplicate_group_409(client: TestClient, auth_headers: Headers) -> None:
    client.post("/api/v1/groups", headers=auth_headers, json={"id": "fleet-a"})
    assert (
        client.post("/api/v1/groups", headers=auth_headers, json={"id": "fleet-a"}).status_code
        == 409
    )


def test_group_device_count(client: TestClient, auth_headers: Headers) -> None:
    client.post("/api/v1/groups", headers=auth_headers, json={"id": "fleet-a"})
    client.post(
        "/api/v1/devices", headers=auth_headers, json={"id": "dev-1", "group_id": "fleet-a"}
    )
    groups = {g["id"]: g for g in client.get("/api/v1/groups", headers=auth_headers).json()["data"]}
    assert groups["fleet-a"]["device_count"] == 1


def test_delete_group_moves_devices_to_default(client: TestClient, auth_headers: Headers) -> None:
    client.post("/api/v1/groups", headers=auth_headers, json={"id": "fleet-a"})
    client.post(
        "/api/v1/devices", headers=auth_headers, json={"id": "dev-1", "group_id": "fleet-a"}
    )
    assert client.delete("/api/v1/groups/fleet-a", headers=auth_headers).status_code == 200
    assert (
        client.get("/api/v1/devices/dev-1", headers=auth_headers).json()["data"]["group_id"]
        == "default"
    )


def test_cannot_delete_default_group(client: TestClient, auth_headers: Headers) -> None:
    assert client.delete("/api/v1/groups/default", headers=auth_headers).status_code == 400
