# app/shadow.py — device shadow: desired/reported, delta, and PATCH-with-retained-publish
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app import mqtt_pub
from app.auth import require_admin
from app.db import get_connection
from app.envelope import ok

log = logging.getLogger("embediq.shadow")

router = APIRouter(prefix="/api/v1", tags=["shadow"], dependencies=[Depends(require_admin)])


def _device_exists(conn: sqlite3.Connection, device_id: str) -> bool:
    return conn.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,)).fetchone() is not None


def load_shadow(conn: sqlite3.Connection, device_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (desired, reported) parsed JSON; empty dicts if there is no shadow row yet."""
    row = conn.execute(
        "SELECT desired, reported FROM device_shadow WHERE device_id = ?", (device_id,)
    ).fetchone()
    if row is None:
        return {}, {}
    return json.loads(row["desired"]), json.loads(row["reported"])


def compute_delta(desired: dict[str, Any], reported: dict[str, Any]) -> dict[str, Any]:
    """Keys in desired whose value differs from (or is absent in) reported."""
    return {key: value for key, value in desired.items() if reported.get(key) != value}


@router.get("/devices/{device_id}/shadow")
def get_shadow(device_id: str) -> dict[str, Any]:
    conn = get_connection()
    try:
        if not _device_exists(conn, device_id):
            raise HTTPException(status_code=404, detail="device not found")
        desired, reported = load_shadow(conn, device_id)
    finally:
        conn.close()
    return ok({"desired": desired, "reported": reported, "delta": compute_delta(desired, reported)})


@router.patch("/devices/{device_id}/shadow/desired")
def patch_desired(device_id: str, delta: dict[str, Any]) -> dict[str, Any]:
    now = int(time.time())
    conn = get_connection()
    try:
        if not _device_exists(conn, device_id):
            raise HTTPException(status_code=404, detail="device not found")
        desired, _reported = load_shadow(conn, device_id)
        desired.update(delta)  # delta semantics: key-level overwrite, never full-replace
        conn.execute(
            "INSERT INTO device_shadow (device_id, desired, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(device_id) DO UPDATE SET "
            "desired = excluded.desired, updated_at = excluded.updated_at",
            (device_id, json.dumps(desired), now),
        )
        conn.commit()
    finally:
        conn.close()
    # Best-effort cloud -> device publish; SQLite is the source of truth.
    try:
        mqtt_pub.publish_retained(f"embediq/{device_id}/state/desired", desired)
    except Exception as exc:
        log.warning("desired publish failed for %s: %s", device_id, exc)
    return ok({"desired": desired})
