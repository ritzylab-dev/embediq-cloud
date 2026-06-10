# tests/integration/sim_device.py — a simulated EmbedIQ device (paho MQTT client)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""A test-only stand-in for real firmware.

It speaks the exact MQTT topic contract from ARCHITECTURE.md so the e2e harness can prove
registry -> bridge -> shadow -> OTA work together without hardware. The real-device run
(HC-5) swaps this class for firmware once firmware Item 6 lands; nothing here is product code.

Topic contract (device id = ``{id}``):
  device -> cloud : embediq/{id}/telemetry, .../status, .../state/reported, .../logs
  cloud -> device : embediq/{id}/state/desired (retained), .../cmd (NOT retained)
"""

from __future__ import annotations

import json
import time
from typing import Any

import paho.mqtt.client as mqtt

# --- pure topic builders (unit-tested without a broker) ---


def telemetry_topic(device_id: str) -> str:
    return f"embediq/{device_id}/telemetry"


def status_topic(device_id: str) -> str:
    return f"embediq/{device_id}/status"


def reported_topic(device_id: str) -> str:
    return f"embediq/{device_id}/state/reported"


def desired_topic(device_id: str) -> str:
    return f"embediq/{device_id}/state/desired"


def cmd_topic(device_id: str) -> str:
    return f"embediq/{device_id}/cmd"


class SimDevice:
    """A paho client that mimics a device: publishes telemetry/status/reported, and captures
    the cloud -> device messages (retained desired + non-retained cmd) it is subscribed to."""

    def __init__(
        self,
        device_id: str,
        host: str,
        port: int,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.device_id = device_id
        self.host = host
        self.port = port
        self._received: list[tuple[str, dict[str, Any]]] = []
        self._connected = False
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=device_id)
        if username is not None:
            self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    # --- callbacks (run on the paho network thread) ---

    def _on_connect(
        self, client: mqtt.Client, _userdata: Any, _flags: Any, _rc: Any, _props: Any
    ) -> None:
        # Subscribe to both cloud -> device channels. ``desired`` is retained, so a late
        # subscriber still receives the last value; ``cmd`` is not, so we subscribe up front.
        client.subscribe(desired_topic(self.device_id), qos=1)
        client.subscribe(cmd_topic(self.device_id), qos=1)
        self._connected = True

    def _on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            data = json.loads(msg.payload)
        except (ValueError, TypeError):
            data = {}
        self._received.append((msg.topic, data if isinstance(data, dict) else {}))

    # --- lifecycle ---

    def connect(self, timeout: float = 15.0) -> None:
        self._client.connect(self.host, self.port, keepalive=30)
        self._client.loop_start()
        deadline = time.monotonic() + timeout
        while not self._connected and time.monotonic() < deadline:
            time.sleep(0.05)
        if not self._connected:
            raise TimeoutError(f"sim device {self.device_id} could not connect to {self.host}")

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    # --- publishing (device -> cloud) ---

    def _publish(self, topic: str, payload: dict[str, Any], *, retain: bool = False) -> None:
        info = self._client.publish(topic, json.dumps(payload), qos=1, retain=retain)
        info.wait_for_publish(timeout=10)

    def publish_telemetry(self, metrics: dict[str, Any], ts: Any = None) -> None:
        body: dict[str, Any] = {"metrics": metrics}
        if ts is not None:
            body["ts"] = ts
        self._publish(telemetry_topic(self.device_id), body)

    def publish_status(self, *, online: bool, firmware_version: str | None = None) -> None:
        body: dict[str, Any] = {"online": online}
        if firmware_version is not None:
            body["firmware_version"] = firmware_version
        self._publish(status_topic(self.device_id), body)

    def publish_reported(self, reported: dict[str, Any]) -> None:
        self._publish(reported_topic(self.device_id), reported)

    # --- inspecting captured cloud -> device messages ---

    def wait_for_message(self, topic: str, timeout: float = 15.0) -> dict[str, Any]:
        """Block until a message on ``topic`` has been captured; return its decoded payload."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for captured_topic, payload in list(self._received):
                if captured_topic == topic:
                    return payload
            time.sleep(0.1)
        raise TimeoutError(f"no message on {topic} within {timeout}s")

    def wait_for_desired(self, timeout: float = 15.0) -> dict[str, Any]:
        return self.wait_for_message(desired_topic(self.device_id), timeout)

    def wait_for_cmd(self, timeout: float = 15.0) -> dict[str, Any]:
        return self.wait_for_message(cmd_topic(self.device_id), timeout)
