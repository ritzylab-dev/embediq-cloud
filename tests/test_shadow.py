# tests/test_shadow.py — device shadow GET/PATCH, delta, and retained publish
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

Headers = dict[str, str]


def _make_device(client: TestClient, headers: Headers, device_id: str = "dev-1") -> None:
    client.post("/api/v1/devices", headers=headers, json={"id": device_id})


def test_get_shadow_empty(client: TestClient, auth_headers: Headers) -> None:
    _make_device(client, auth_headers)
    resp = client.get("/api/v1/devices/dev-1/shadow", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {"desired": {}, "reported": {}, "delta": {}}


def test_get_shadow_delta(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import mqtt_pub

    monkeypatch.setattr(mqtt_pub, "publish_retained", Mock())
    _make_device(client, auth_headers)
    # desired: mode=run, level=5 ; reported (set directly): mode=run, level=3
    client.patch(
        "/api/v1/devices/dev-1/shadow/desired",
        headers=auth_headers,
        json={"mode": "run", "level": 5},
    )
    from app.db import get_connection

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE device_shadow SET reported = ? WHERE device_id = 'dev-1'",
            (json.dumps({"mode": "run", "level": 3}),),
        )
        conn.commit()
    finally:
        conn.close()
    data = client.get("/api/v1/devices/dev-1/shadow", headers=auth_headers).json()["data"]
    assert data["desired"] == {"mode": "run", "level": 5}
    assert data["reported"] == {"mode": "run", "level": 3}
    assert data["delta"] == {"level": 5}  # only the differing key


def test_get_shadow_unknown_device_404(client: TestClient, auth_headers: Headers) -> None:
    assert client.get("/api/v1/devices/ghost/shadow", headers=auth_headers).status_code == 404


def test_patch_merges_delta_and_publishes(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import mqtt_pub

    pub = Mock()
    monkeypatch.setattr(mqtt_pub, "publish_retained", pub)
    _make_device(client, auth_headers)
    client.patch(
        "/api/v1/devices/dev-1/shadow/desired", headers=auth_headers, json={"a": 1, "b": 2}
    )
    resp = client.patch("/api/v1/devices/dev-1/shadow/desired", headers=auth_headers, json={"b": 9})
    assert resp.status_code == 200
    # delta semantics: a preserved, b overwritten
    assert resp.json()["data"]["desired"] == {"a": 1, "b": 9}
    # published the FULL merged desired to the right topic, retained
    pub.assert_called_with("embediq/dev-1/state/desired", {"a": 1, "b": 9})


def test_patch_resilient_to_broker_down(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import mqtt_pub

    monkeypatch.setattr(mqtt_pub, "publish_retained", Mock(side_effect=RuntimeError("broker down")))
    _make_device(client, auth_headers)
    resp = client.patch("/api/v1/devices/dev-1/shadow/desired", headers=auth_headers, json={"x": 1})
    assert resp.status_code == 200  # publish failure does not fail the request
    # SQLite is the source of truth — the write persisted
    got = client.get("/api/v1/devices/dev-1/shadow", headers=auth_headers).json()["data"]
    assert got["desired"] == {"x": 1}


def test_patch_unknown_device_404(client: TestClient, auth_headers: Headers) -> None:
    assert (
        client.patch(
            "/api/v1/devices/ghost/shadow/desired", headers=auth_headers, json={"x": 1}
        ).status_code
        == 404
    )


def test_device_detail_includes_shadow(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import mqtt_pub

    monkeypatch.setattr(mqtt_pub, "publish_retained", Mock())
    _make_device(client, auth_headers)
    client.patch("/api/v1/devices/dev-1/shadow/desired", headers=auth_headers, json={"mode": "run"})
    data = client.get("/api/v1/devices/dev-1", headers=auth_headers).json()["data"]
    assert data["shadow"] == {"desired": {"mode": "run"}, "reported": {}}


def test_publish_retained_uses_retain_qos1(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import mqtt_pub

    fake = Mock()
    monkeypatch.setattr(mqtt_pub, "_get_client", lambda: fake)
    mqtt_pub.publish_retained("embediq/dev-1/state/desired", {"a": 1})
    fake.publish.assert_called_once_with(
        "embediq/dev-1/state/desired", json.dumps({"a": 1}), qos=1, retain=True
    )
