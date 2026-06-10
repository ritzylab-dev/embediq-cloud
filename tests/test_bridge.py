# tests/test_bridge.py — MQTT bridge routing (pure function, no live broker)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import bridge
from app.db import get_connection
from app.registry import create_device


def _seed_device(device_id: str) -> None:
    conn = get_connection()
    try:
        create_device(conn, device_id)
        conn.commit()
    finally:
        conn.close()


def test_telemetry_routes_to_influx(monkeypatch: pytest.MonkeyPatch) -> None:
    influx = Mock()
    monkeypatch.setattr(bridge, "influx", influx)
    payload = json.dumps({"ts": 123, "metrics": {"temp": 21.5, "hum": 40}}).encode()
    bridge.route_message("embediq/dev-1/telemetry", payload)
    influx.write.assert_called_once_with("dev-1", 123, {"temp": 21.5, "hum": 40})


def test_telemetry_point_shape() -> None:
    point = bridge.build_telemetry_point("dev-1", 123, {"temp": 21.5})
    line = point.to_line_protocol()
    assert line.startswith("telemetry,device_id=dev-1")
    assert "temp=21.5" in line


def test_logs_routes_to_loki(monkeypatch: pytest.MonkeyPatch) -> None:
    loki = Mock()
    monkeypatch.setattr(bridge, "loki", loki)
    payload = json.dumps({"level": "error", "message": "boom"}).encode()
    bridge.route_message("embediq/dev-1/logs", payload)
    loki.push.assert_called_once_with("dev-1", "error", "boom")


def test_state_reported_updates_db(temp_db: None) -> None:
    _seed_device("dev-1")
    bridge.route_message(
        "embediq/dev-1/state/reported", json.dumps({"fw": "1.2.3", "mode": "run"}).encode()
    )
    conn = get_connection()
    try:
        shadow = conn.execute(
            "SELECT reported FROM device_shadow WHERE device_id = 'dev-1'"
        ).fetchone()
        state = conn.execute(
            "SELECT last_seen FROM device_state WHERE device_id = 'dev-1'"
        ).fetchone()
    finally:
        conn.close()
    assert json.loads(shadow["reported"]) == {"fw": "1.2.3", "mode": "run"}
    assert state["last_seen"] is not None


def test_status_upserts_db(temp_db: None) -> None:
    _seed_device("dev-1")
    bridge.route_message(
        "embediq/dev-1/status",
        json.dumps(
            {"online": True, "ip_address": "10.0.0.5", "firmware_version": "1.2.3"}
        ).encode(),
    )
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT online, ip_address, firmware_version, last_seen "
            "FROM device_state WHERE device_id = 'dev-1'"
        ).fetchone()
    finally:
        conn.close()
    assert row["online"] == 1
    assert row["ip_address"] == "10.0.0.5"
    assert row["firmware_version"] == "1.2.3"
    assert row["last_seen"] is not None


def test_cmd_and_desired_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    influx, loki = Mock(), Mock()
    monkeypatch.setattr(bridge, "influx", influx)
    monkeypatch.setattr(bridge, "loki", loki)
    bridge.route_message("embediq/dev-1/cmd", json.dumps({"action": "reboot"}).encode())
    bridge.route_message("embediq/dev-1/state/desired", json.dumps({"mode": "run"}).encode())
    influx.write.assert_not_called()
    loki.push.assert_not_called()


def test_bad_json_and_unknown_topic_no_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    influx, loki = Mock(), Mock()
    monkeypatch.setattr(bridge, "influx", influx)
    monkeypatch.setattr(bridge, "loki", loki)
    bridge.route_message("embediq/dev-1/telemetry", b"not-json")
    bridge.route_message("embediq/dev-1/mystery", json.dumps({"x": 1}).encode())
    bridge.route_message("totally/wrong", b"{}")
    influx.write.assert_not_called()
    loki.push.assert_not_called()


def test_bridge_disabled_skips_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_PASS_HASH", "x")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "d.db"))
    monkeypatch.setenv("BRIDGE_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    started = Mock()
    monkeypatch.setattr(bridge, "start_bridge", started)
    from app.main import app

    with TestClient(app):
        pass
    started.assert_not_called()
