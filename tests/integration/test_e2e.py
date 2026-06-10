# tests/integration/test_e2e.py — end-to-end: registry -> bridge -> shadow -> OTA (simulated device)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""The cloud-side proof that the whole stack works together, driven by a simulated device.

Run only in the CI ``integration`` job (the unit run excludes the ``integration`` marker).
The real-device version (HC-5) swaps ``SimDevice`` for firmware once firmware Item 6 lands.

Honest seams (documented in the PR, not worked around):
- Broker auth: Mosquitto still runs ``allow_anonymous true`` (the go-auth plugin -> /internal/auth
  wiring is deferred to PR-SEC / T1.10). So we assert the /internal/auth *contract* directly
  (allow a registered device, deny an unknown one) — the broker will call it once T1.10 wires it.
- OTA deploy: app.hawkbit.create_deployment targets a non-standard endpoint and the Hawkbit
  deployment-ready -> callback auto-wiring is not present in the OSS stack. So step 7 proves the
  two real contracts: the firmware upload proxy against live Hawkbit, and the cloud -> device
  OTA-notify relay (/internal/hawkbit-callback) delivering ota_check on the device cmd topic.
"""

from __future__ import annotations

import time

import httpx
import pytest

from tests.integration.conftest import StackConfig, influx_count, internal_headers
from tests.integration.sim_device import SimDevice, cmd_topic

pytestmark = pytest.mark.integration

DEVICE_ID = "e2e-sim-01"
DEVICE_PASSWORD = "device-secret"
FIRMWARE_VERSION = "1.4.2"


@pytest.fixture
def device(api: httpx.Client, auth_headers: dict[str, str]) -> str:
    """Step 2 — register a password-auth test device (idempotent across reruns)."""
    api.delete(f"/api/v1/devices/{DEVICE_ID}", headers=auth_headers)
    resp = api.post(
        "/api/v1/devices",
        headers=auth_headers,
        json={"id": DEVICE_ID, "password": DEVICE_PASSWORD},
    )
    assert resp.status_code == 201, f"register failed: {resp.status_code} {resp.text}"
    return DEVICE_ID


def test_step3_internal_auth_contract(cfg: StackConfig, api: httpx.Client, device: str) -> None:
    """Step 3 — the device-auth contract the broker plugin will call, exercised with the shared
    secret (X-Internal-Key) so CI runs the enforced path (PR-SEC2)."""
    keyed = internal_headers(cfg)
    allow = api.post(
        "/internal/auth", json={"username": device, "password": DEVICE_PASSWORD}, headers=keyed
    )
    assert allow.status_code == 200
    assert allow.json()["data"]["result"] == "allow"

    deny = api.post("/internal/auth", json={"username": device, "password": "wrong"}, headers=keyed)
    assert deny.status_code == 403

    # When the secret is enforced, an unkeyed call is rejected outright (401).
    if cfg.internal_key:
        unkeyed = api.post("/internal/auth", json={"username": device, "password": DEVICE_PASSWORD})
        assert unkeyed.status_code == 401


def test_step4_telemetry_lands_in_influx(cfg: StackConfig, api: httpx.Client, device: str) -> None:
    """Step 4 — sim device publishes telemetry; the bridge writes a point to InfluxDB."""
    sim = SimDevice(device, cfg.mqtt_host, cfg.mqtt_port, username=device, password=DEVICE_PASSWORD)
    sim.connect()
    try:
        # Republish a few times: the bridge subscribes on connect, so guard the connect race.
        for _ in range(5):
            sim.publish_telemetry({"temp_c": 21.5, "rssi": -57})
            if influx_count(cfg, device, timeout=6) > 0:
                break
        assert influx_count(cfg, device, timeout=20) > 0, "no telemetry point reached InfluxDB"
    finally:
        sim.disconnect()


def test_step5_status_marks_device_online(
    cfg: StackConfig, api: httpx.Client, auth_headers: dict[str, str], device: str
) -> None:
    """Step 5 — sim device reports status online + firmware; the API reflects it."""
    sim = SimDevice(device, cfg.mqtt_host, cfg.mqtt_port, username=device, password=DEVICE_PASSWORD)
    sim.connect()
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            sim.publish_status(online=True, firmware_version=FIRMWARE_VERSION)
            state = api.get(f"/api/v1/devices/{device}", headers=auth_headers).json()["data"][
                "state"
            ]
            if state["online"] and state["firmware_version"] == FIRMWARE_VERSION:
                break
            time.sleep(1)
        assert state["online"] is True
        assert state["firmware_version"] == FIRMWARE_VERSION
    finally:
        sim.disconnect()


def test_step6_shadow_desired_reported_roundtrip(
    cfg: StackConfig, api: httpx.Client, auth_headers: dict[str, str], device: str
) -> None:
    """Step 6 — PATCH desired -> sim receives retained desired -> reports it -> API reflects."""
    sim = SimDevice(device, cfg.mqtt_host, cfg.mqtt_port, username=device, password=DEVICE_PASSWORD)
    sim.connect()
    try:
        patch = api.patch(
            f"/api/v1/devices/{device}/shadow/desired",
            headers=auth_headers,
            json={"sample_rate": 30},
        )
        assert patch.status_code == 200

        desired = sim.wait_for_desired(timeout=20)
        assert desired.get("sample_rate") == 30

        # The device acknowledges by reporting the applied value.
        sim.publish_reported({"sample_rate": 30})

        deadline = time.monotonic() + 20
        reported: dict[str, object] = {}
        while time.monotonic() < deadline:
            shadow = api.get(f"/api/v1/devices/{device}/shadow", headers=auth_headers).json()[
                "data"
            ]
            reported = shadow["reported"]
            if reported.get("sample_rate") == 30:
                break
            time.sleep(1)
        assert reported.get("sample_rate") == 30
    finally:
        sim.disconnect()


def test_step7_ota_upload_and_notify(
    cfg: StackConfig, api: httpx.Client, auth_headers: dict[str, str], device: str
) -> None:
    """Step 7 — upload firmware to live Hawkbit, then relay an OTA notify to the device cmd topic.

    Two real contracts: (a) the Hawkbit upload proxy works against the live broker; (b) the
    cloud -> device OTA-notify relay delivers ota_check on the (non-retained) cmd topic. See the
    module docstring for why the literal /ota/deploy auto-callback chain is out of e2e scope.
    """
    sim = SimDevice(device, cfg.mqtt_host, cfg.mqtt_port, username=device, password=DEVICE_PASSWORD)
    sim.connect()
    try:
        # (a) Wait for Hawkbit to be reachable through the proxy, then upload a firmware module.
        deadline = time.monotonic() + 180
        firmware_id: int | None = None
        while time.monotonic() < deadline:
            upload = api.post(
                "/api/v1/ota/firmware",
                headers=auth_headers,
                data={"name": "e2e-fw", "version": FIRMWARE_VERSION},
                files={"file": ("fw.bin", b"\x00fake-firmware-image\x00")},
            )
            if upload.status_code == 201:
                firmware_id = upload.json()["data"]["id"]
                break
            time.sleep(3)  # Hawkbit (Spring Boot) takes time to come up
        assert firmware_id is not None, "Hawkbit firmware upload never succeeded via the proxy"

        # (b) Relay the OTA notification (the production cloud -> device path) and assert receipt.
        # /internal/hawkbit-callback also enforces the shared secret when INTERNAL_API_KEY is set.
        relay = api.post(
            "/internal/hawkbit-callback",
            json={
                "device_id": device,
                "firmware_id": firmware_id,
                "version": FIRMWARE_VERSION,
                "url": "http://hawkbit/fw.bin",
                "checksum": "sha256:deadbeef",
            },
            headers=internal_headers(cfg),
        )
        assert relay.status_code == 200

        cmd = sim.wait_for_cmd(timeout=20)
        assert cmd.get("cmd") == "ota_check"
        assert cmd.get("version") == FIRMWARE_VERSION
        assert cmd.get("firmware_id") == firmware_id
    finally:
        sim.disconnect()


def test_cmd_topic_builder_matches_contract() -> None:
    """Cheap guard that the helper builds the exact cmd topic the API publishes to."""
    assert cmd_topic(DEVICE_ID) == f"embediq/{DEVICE_ID}/cmd"
