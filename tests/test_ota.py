# tests/test_ota.py — OTA proxy, cmd relay, admin cmd, and bridge OTA feedback
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
import json
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import get_connection
from app.registry import create_device

Headers = dict[str, str]


def _seed(device_id: str = "dev-1") -> None:
    conn = get_connection()
    try:
        create_device(conn, device_id)
        conn.commit()
    finally:
        conn.close()


# --- OTA proxy (mock app.hawkbit functions) ---


def test_list_firmware(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import hawkbit

    monkeypatch.setattr(
        hawkbit,
        "list_software_modules",
        Mock(
            return_value=[
                {"id": 1, "name": "fw", "version": "1.0", "size_bytes": 10, "created_at": 5}
            ]
        ),
    )
    resp = client.get("/api/v1/ota/firmware", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"][0]["name"] == "fw"


def test_post_firmware_calls_hawkbit(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import hawkbit

    create = Mock(return_value={"id": 5})
    upload = Mock()
    monkeypatch.setattr(hawkbit, "create_software_module", create)
    monkeypatch.setattr(hawkbit, "upload_artifact", upload)
    resp = client.post(
        "/api/v1/ota/firmware",
        headers=auth_headers,
        data={"name": "fw", "version": "2.0"},
        files={"file": ("fw.bin", b"binarydata")},
    )
    assert resp.status_code == 201
    create.assert_called_once_with("fw", "2.0")
    upload.assert_called_once()


def test_deploy_calls_hawkbit(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import hawkbit

    deploy = Mock(return_value={"id": 9})
    monkeypatch.setattr(hawkbit, "create_deployment", deploy)
    resp = client.post(
        "/api/v1/ota/deploy", headers=auth_headers, json={"firmware_id": 5, "device_id": "dev-1"}
    )
    assert resp.status_code == 200
    deploy.assert_called_once()


def test_status_maps_hawkbit(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import hawkbit

    monkeypatch.setattr(
        hawkbit,
        "deployment_status",
        Mock(
            return_value={
                "status": "running",
                "progress_pct": 50,
                "version": "2.0",
                "updated_at": 7,
            }
        ),
    )
    data = client.get("/api/v1/ota/status/dev-1", headers=auth_headers).json()["data"]
    assert data["status"] == "running"
    assert data["progress_pct"] == 50


def test_hawkbit_error_becomes_envelope(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import hawkbit
    from app.hawkbit import HawkbitError

    monkeypatch.setattr(
        hawkbit, "list_software_modules", Mock(side_effect=HawkbitError(502, "down"))
    )
    resp = client.get("/api/v1/ota/firmware", headers=auth_headers)
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "bad_gateway"


# --- cmd relay (mock the publisher) ---


def test_callback_relays_ota_check_non_retained(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import mqtt_pub

    pub = Mock()
    monkeypatch.setattr(mqtt_pub, "publish", pub)
    body = {
        "device_id": "dev-1",
        "firmware_id": 5,
        "url": "http://hawkbit/fw.bin",
        "checksum": "sha256:abc",
        "version": "2.0",
    }
    resp = client.post("/internal/hawkbit-callback", json=body)
    assert resp.status_code == 200
    pub.assert_called_once_with(
        "embediq/dev-1/cmd",
        {
            "cmd": "ota_check",
            "firmware_id": 5,
            "url": "http://hawkbit/fw.bin",
            "checksum": "sha256:abc",
            "version": "2.0",
        },
        retain=False,
    )


# --- admin device command ---


def test_admin_cmd_publishes_non_retained(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import mqtt_pub

    pub = Mock()
    monkeypatch.setattr(mqtt_pub, "publish", pub)
    client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-1"})
    resp = client.post("/api/v1/devices/dev-1/cmd", headers=auth_headers, json={"cmd": "reboot"})
    assert resp.status_code == 200
    pub.assert_called_once_with("embediq/dev-1/cmd", {"cmd": "reboot"}, retain=False)


def test_admin_cmd_with_params(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import mqtt_pub

    pub = Mock()
    monkeypatch.setattr(mqtt_pub, "publish", pub)
    client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-1"})
    resp = client.post(
        "/api/v1/devices/dev-1/cmd",
        headers=auth_headers,
        json={"cmd": "ota_check", "params": {"firmware_id": 5}},
    )
    assert resp.status_code == 200
    pub.assert_called_once_with(
        "embediq/dev-1/cmd", {"cmd": "ota_check", "firmware_id": 5}, retain=False
    )


def test_admin_cmd_invalid_400(client: TestClient, auth_headers: Headers) -> None:
    client.post("/api/v1/devices", headers=auth_headers, json={"id": "dev-1"})
    assert (
        client.post(
            "/api/v1/devices/dev-1/cmd", headers=auth_headers, json={"cmd": "explode"}
        ).status_code
        == 400
    )


def test_admin_cmd_unknown_device_404(client: TestClient, auth_headers: Headers) -> None:
    assert (
        client.post(
            "/api/v1/devices/ghost/cmd", headers=auth_headers, json={"cmd": "reboot"}
        ).status_code
        == 404
    )


def test_admin_cmd_requires_jwt(client: TestClient) -> None:
    assert client.post("/api/v1/devices/dev-1/cmd", json={"cmd": "reboot"}).status_code == 401


# --- bridge OTA feedback (status handler extension) ---


def test_feedback_installed_updates_fw_and_forwards(
    temp_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import bridge, hawkbit

    finished = Mock()
    monkeypatch.setattr(hawkbit, "mark_finished", finished)
    _seed("dev-1")
    bridge.route_message(
        "embediq/dev-1/status",
        json.dumps({"online": True, "ota_status": "installed", "version": "2.0.0"}).encode(),
    )
    conn = get_connection()
    try:
        fw = conn.execute(
            "SELECT firmware_version FROM device_state WHERE device_id = 'dev-1'"
        ).fetchone()["firmware_version"]
    finally:
        conn.close()
    assert fw == "2.0.0"
    finished.assert_called_once_with("dev-1")


def test_feedback_failed_forwards(temp_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import bridge, hawkbit

    failed = Mock()
    monkeypatch.setattr(hawkbit, "mark_failed", failed)
    _seed("dev-1")
    bridge.route_message(
        "embediq/dev-1/status",
        json.dumps({"online": True, "ota_status": "failed", "reason": "crc-mismatch"}).encode(),
    )
    failed.assert_called_once()


# --- hawkbit client unit tests (mock httpx, cover the client mapping) ---


def test_hawkbit_list_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import hawkbit

    resp = Mock()
    resp.json.return_value = {
        "content": [{"id": 1, "name": "fw", "version": "1.0", "size": 99, "createdAt": 5}]
    }
    monkeypatch.setattr(hawkbit, "_request", Mock(return_value=resp))
    assert hawkbit.list_software_modules() == [
        {"id": 1, "name": "fw", "version": "1.0", "size_bytes": 99, "created_at": 5}
    ]


def test_hawkbit_request_raises_on_connect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import hawkbit

    def boom(*_args: object, **_kwargs: object) -> object:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "request", boom)
    with pytest.raises(hawkbit.HawkbitError):
        hawkbit._request("GET", "/rest/v1/softwaremodules")
