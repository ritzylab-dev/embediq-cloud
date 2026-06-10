# app/mqtt_pub.py — cloud->device retained publisher (separate from the consumer-only bridge)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

from app.config import get_bridge_settings

log = logging.getLogger("embediq.mqtt_pub")

# A single lazily-created publisher client. This is the cloud -> device path; the bridge
# (app/bridge.py) stays consumer-only (R-2) and must never publish.
_client: mqtt.Client | None = None


def _get_client() -> mqtt.Client:
    global _client
    if _client is None:
        settings = get_bridge_settings()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if settings.MQTT_USERNAME:
            client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.connect_async(settings.MQTT_HOST, settings.MQTT_PORT)
        client.loop_start()
        _client = client
    return _client


def publish(topic: str, payload: dict[str, Any], retain: bool = False) -> None:
    """Publish JSON to `topic` at QoS 1. Best-effort: never raises.

    `retain=True` for state (shadow desired); `retain=False` for commands (`cmd`), which
    must never be retained. SQLite/Hawkbit remain the sources of truth.
    """
    try:
        _get_client().publish(topic, json.dumps(payload), qos=1, retain=retain)
    except Exception as exc:
        log.warning("publish to %s failed: %s", topic, exc)


def publish_retained(topic: str, payload: dict[str, Any]) -> None:
    """Publish JSON to `topic` with retain=True (shadow desired state)."""
    publish(topic, payload, retain=True)
