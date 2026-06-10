# app/bridge.py — consumer-only MQTT bridge: routes device messages to storage backends
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

import httpx
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from app import hawkbit
from app.config import get_bridge_settings
from app.db import get_connection

log = logging.getLogger("embediq.bridge")

# Subscribe broadly; route by topic suffix. The bridge NEVER publishes (consumer-only, R-2).
SUBSCRIBE_TOPIC = "embediq/+/#"
QOS = 1
IGNORED_CHANNELS = ("cmd", "state/desired")  # cloud -> device direction


def build_telemetry_point(device_id: str, ts: Any, metrics: dict[str, Any]) -> Point:
    point = Point("telemetry").tag("device_id", device_id)
    for key, value in metrics.items():
        point = point.field(key, value)
    if ts is not None:
        point = point.time(ts)
    return point


class InfluxBackend:
    def __init__(self) -> None:
        settings = get_bridge_settings()
        self._client = InfluxDBClient(
            url=settings.INFLUX_URL, token=settings.INFLUX_TOKEN, org=settings.INFLUX_ORG
        )
        self._bucket = settings.INFLUX_BUCKET
        self._org = settings.INFLUX_ORG
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

    def write(self, device_id: str, ts: Any, metrics: dict[str, Any]) -> None:
        try:
            point = build_telemetry_point(device_id, ts, metrics)
            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
        except Exception as exc:  # best-effort: a down/erroring InfluxDB must not break the loop
            log.warning("influx write failed for %s: %s", device_id, exc)


class LokiBackend:
    def __init__(self) -> None:
        self._url = get_bridge_settings().LOKI_URL.rstrip("/") + "/loki/api/v1/push"

    def push(self, device_id: str, level: str, message: str) -> None:
        payload = {
            "streams": [
                {
                    "stream": {"device_id": device_id, "level": level},
                    "values": [[str(time.time_ns()), message]],
                }
            ]
        }
        try:
            httpx.post(self._url, json=payload, timeout=5.0)
        except Exception as exc:  # best-effort
            log.warning("loki push failed for %s: %s", device_id, exc)


# Lazily-constructed, module-level backends (tests replace these with mocks).
influx: InfluxBackend | None = None
loki: LokiBackend | None = None


def _influx() -> InfluxBackend:
    global influx
    if influx is None:
        influx = InfluxBackend()
    return influx


def _loki() -> LokiBackend:
    global loki
    if loki is None:
        loki = LokiBackend()
    return loki


def _handle_telemetry(device_id: str, data: dict[str, Any]) -> None:
    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        log.warning("telemetry from %s missing a metrics object", device_id)
        return
    _influx().write(device_id, data.get("ts"), metrics)


def _handle_logs(device_id: str, data: dict[str, Any]) -> None:
    _loki().push(device_id, str(data.get("level", "info")), str(data.get("message", "")))


def _handle_reported(device_id: str, data: dict[str, Any]) -> None:
    now = int(time.time())
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO device_shadow (device_id, reported, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(device_id) DO UPDATE SET "
            "reported = excluded.reported, updated_at = excluded.updated_at",
            (device_id, json.dumps(data), now),
        )
        conn.execute("UPDATE device_state SET last_seen = ? WHERE device_id = ?", (now, device_id))
        conn.commit()
    except sqlite3.Error as exc:
        log.warning("reported update failed for %s: %s", device_id, exc)
    finally:
        conn.close()


def _handle_status(device_id: str, data: dict[str, Any]) -> None:
    now = int(time.time())
    online = 1 if data.get("online") else 0
    ota_status = data.get("ota_status")
    version = data.get("version")
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO device_state (device_id, online, ip_address, firmware_version, last_seen) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(device_id) DO UPDATE SET "
            "online = excluded.online, "
            "ip_address = COALESCE(excluded.ip_address, ip_address), "
            "firmware_version = COALESCE(excluded.firmware_version, firmware_version), "
            "last_seen = excluded.last_seen",
            (device_id, online, data.get("ip_address"), data.get("firmware_version"), now),
        )
        if ota_status == "installed" and version is not None:
            conn.execute(
                "UPDATE device_state SET firmware_version = ? WHERE device_id = ?",
                (version, device_id),
            )
        conn.commit()
    except sqlite3.Error as exc:
        log.warning("status update failed for %s: %s", device_id, exc)
    finally:
        conn.close()
    # OTA feedback → forward to Hawkbit (REST, not an MQTT publish — bridge stays consumer-only).
    if ota_status == "installed":
        hawkbit.mark_finished(device_id)
    elif ota_status == "failed":
        hawkbit.mark_failed(device_id, str(data.get("reason", "")))


def route_message(topic: str, payload: bytes) -> None:
    """Pure routing entrypoint the paho callback calls. Never raises on bad input."""
    parts = topic.split("/")
    if len(parts) < 3 or parts[0] != "embediq":
        log.warning("ignoring message on unexpected topic: %s", topic)
        return
    device_id = parts[1]
    channel = "/".join(parts[2:])
    if channel in IGNORED_CHANNELS:
        return  # consumer-only: never act on cloud -> device topics
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        log.warning("dropping malformed JSON on topic %s", topic)
        return
    if not isinstance(data, dict):
        log.warning("dropping non-object payload on topic %s", topic)
        return
    if channel == "telemetry":
        _handle_telemetry(device_id, data)
    elif channel == "logs":
        _handle_logs(device_id, data)
    elif channel == "state/reported":
        _handle_reported(device_id, data)
    elif channel == "status":
        _handle_status(device_id, data)
    else:
        log.warning("ignoring unknown channel '%s' on topic %s", channel, topic)


# --- broker connection (background thread; non-blocking; auto-reconnect) ---

_client: mqtt.Client | None = None


def _on_connect(
    client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _props: Any
) -> None:
    log.info("bridge connected (rc=%s); subscribing to %s", reason_code, SUBSCRIBE_TOPIC)
    client.subscribe(SUBSCRIBE_TOPIC, qos=QOS)


def _on_message(_client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
    try:
        route_message(msg.topic, msg.payload)
    except Exception as exc:  # a single bad message must never kill the loop
        log.warning("route_message error on %s: %s", msg.topic, exc)


def start_bridge() -> None:
    """Start the paho client in a background thread. Non-blocking even if the broker is down."""
    global _client
    settings = get_bridge_settings()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = _on_connect
    client.on_message = _on_message
    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    try:
        client.connect_async(settings.MQTT_HOST, settings.MQTT_PORT)
        client.loop_start()
    except Exception as exc:  # never let bridge startup crash the app
        log.warning("bridge failed to start: %s", exc)
    _client = client
    log.info("bridge started (host=%s port=%s)", settings.MQTT_HOST, settings.MQTT_PORT)


def stop_bridge() -> None:
    global _client
    if _client is None:
        return
    try:
        _client.loop_stop()
        _client.disconnect()
    except Exception as exc:
        log.warning("bridge stop error: %s", exc)
    _client = None
