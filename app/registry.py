# app/registry.py — device registry, groups, and system endpoints (all behind require_admin)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography import x509
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import __version__
from app.auth import hash_password, require_admin
from app.config import get_cert_warn_days
from app.db import get_connection
from app.envelope import ok

CA_CERT_PATH = Path("/certs/ca.crt")
_START_TIME = time.time()

router = APIRouter(prefix="/api/v1", tags=["registry"], dependencies=[Depends(require_admin)])


class DeviceExists(Exception):
    """Raised when creating a device id that already exists."""


class DeviceCreate(BaseModel):
    id: str
    cert_cn: str | None = None
    password: str | None = None
    group_id: str = "default"
    attributes: dict[str, Any] = {}


class DevicePatch(BaseModel):
    attributes: dict[str, Any] | None = None
    group_id: str | None = None


class GroupCreate(BaseModel):
    id: str
    description: str | None = None


def create_device(
    conn: sqlite3.Connection,
    device_id: str,
    *,
    cert_cn: str | None = None,
    password: str | None = None,
    group_id: str = "default",
    attributes: dict[str, Any] | None = None,
) -> None:
    """Insert a device + its device_state row. Shared with PR-B3 auto-registration.

    Operates within the caller's connection (no commit) so it composes in a transaction.
    """
    if conn.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,)).fetchone() is not None:
        raise DeviceExists(device_id)
    password_hash = hash_password(password) if password else None
    conn.execute(
        "INSERT INTO devices (id, cert_cn, password_hash, group_id, attributes, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            device_id,
            cert_cn,
            password_hash,
            group_id,
            json.dumps(attributes or {}),
            int(time.time()),
        ),
    )
    conn.execute("INSERT INTO device_state (device_id, online) VALUES (?, 0)", (device_id,))


# --- devices ---


@router.get("/devices")
def list_devices() -> dict[str, Any]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT d.id, d.group_id, ds.online, ds.last_seen, ds.firmware_version "
            "FROM devices d LEFT JOIN device_state ds ON ds.device_id = d.id ORDER BY d.id"
        ).fetchall()
    finally:
        conn.close()
    return ok(
        [
            {
                "id": r["id"],
                "online": bool(r["online"]),
                "last_seen": r["last_seen"],
                "group_id": r["group_id"],
                "firmware_version": r["firmware_version"],
            }
            for r in rows
        ]
    )


@router.get("/devices/{device_id}")
def get_device(device_id: str) -> dict[str, Any]:
    conn = get_connection()
    try:
        dev = conn.execute(
            "SELECT id, group_id, attributes FROM devices WHERE id = ?", (device_id,)
        ).fetchone()
        if dev is None:
            raise HTTPException(status_code=404, detail="device not found")
        state = conn.execute(
            "SELECT online, last_seen, ip_address, firmware_version "
            "FROM device_state WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        shadow = conn.execute(
            "SELECT desired, reported FROM device_shadow WHERE device_id = ?", (device_id,)
        ).fetchone()
    finally:
        conn.close()
    return ok(
        {
            "id": dev["id"],
            "group_id": dev["group_id"],
            "attributes": json.loads(dev["attributes"]),
            "state": {
                "online": bool(state["online"]) if state else False,
                "last_seen": state["last_seen"] if state else None,
                "ip_address": state["ip_address"] if state else None,
                "firmware_version": state["firmware_version"] if state else None,
            },
            "shadow": {
                "desired": json.loads(shadow["desired"]) if shadow else {},
                "reported": json.loads(shadow["reported"]) if shadow else {},
            },
        }
    )


@router.post("/devices", status_code=201)
def post_device(body: DeviceCreate) -> dict[str, Any]:
    conn = get_connection()
    try:
        create_device(
            conn,
            body.id,
            cert_cn=body.cert_cn,
            password=body.password,
            group_id=body.group_id,
            attributes=body.attributes,
        )
        conn.commit()
    except DeviceExists as exc:
        raise HTTPException(status_code=409, detail="device id already exists") from exc
    finally:
        conn.close()
    return ok({"id": body.id})


@router.patch("/devices/{device_id}")
def patch_device(device_id: str, body: DevicePatch) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="device not found")
        if "group_id" in fields and fields["group_id"] is not None:
            conn.execute(
                "UPDATE devices SET group_id = ? WHERE id = ?", (fields["group_id"], device_id)
            )
        if "attributes" in fields and fields["attributes"] is not None:
            conn.execute(
                "UPDATE devices SET attributes = ? WHERE id = ?",
                (json.dumps(fields["attributes"]), device_id),
            )
        conn.commit()
    finally:
        conn.close()
    return ok({"id": device_id})


@router.delete("/devices/{device_id}")
def delete_device(device_id: str) -> dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="device not found")
    finally:
        conn.close()
    return ok({"id": device_id})


# --- groups ---


@router.get("/groups")
def list_groups() -> dict[str, Any]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT g.id, g.description, COUNT(d.id) AS device_count "
            "FROM groups g LEFT JOIN devices d ON d.group_id = g.id GROUP BY g.id ORDER BY g.id"
        ).fetchall()
    finally:
        conn.close()
    return ok(
        [
            {"id": r["id"], "description": r["description"], "device_count": r["device_count"]}
            for r in rows
        ]
    )


@router.post("/groups", status_code=201)
def post_group(body: GroupCreate) -> dict[str, Any]:
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM groups WHERE id = ?", (body.id,)).fetchone() is not None:
            raise HTTPException(status_code=409, detail="group id already exists")
        conn.execute(
            "INSERT INTO groups (id, description, created_at) VALUES (?, ?, ?)",
            (body.id, body.description, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    return ok({"id": body.id})


@router.delete("/groups/{group_id}")
def delete_group(group_id: str) -> dict[str, Any]:
    if group_id == "default":
        raise HTTPException(status_code=400, detail="the default group cannot be deleted")
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="group not found")
        conn.execute("UPDATE devices SET group_id = 'default' WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.commit()
    finally:
        conn.close()
    return ok({"id": group_id})


# --- system ---


@router.get("/system/health")
def system_health() -> dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM device_state WHERE online = 1").fetchone()
    finally:
        conn.close()
    return ok(
        {
            "status": "ok",
            "devices_online": row["n"],
            "uptime_s": int(time.time() - _START_TIME),
            "version": __version__,
        }
    )


@router.get("/system/certs")
def system_certs() -> dict[str, Any]:
    warn_days = get_cert_warn_days()
    if not CA_CERT_PATH.exists():
        return ok(
            {
                "ca_cert_pem": None,
                "expires_in_days": None,
                "warning": False,
                "warning_days": warn_days,
            }
        )
    pem = CA_CERT_PATH.read_text(encoding="utf-8")
    expires_in_days: int | None = None
    try:
        cert = x509.load_pem_x509_certificate(pem.encode())
        expires_in_days = (cert.not_valid_after_utc - datetime.now(UTC)).days
    except ValueError:
        expires_in_days = None
    warning = expires_in_days is not None and expires_in_days <= warn_days
    return ok(
        {
            "ca_cert_pem": pem,
            "expires_in_days": expires_in_days,
            "warning": warning,
            "warning_days": warn_days,
        }
    )


@router.post("/system/certs/rotate")
def rotate_certs() -> dict[str, Any]:
    """Record a manual CA-rotation trigger (OSS: track + trigger only).

    The cloud tracks the request; the actual CA file regeneration is an operator step
    (scripts/gen-certs.sh) and the device-side atomic rotation is firmware EST (HC-6).
    Deterministic rule executes here — no AI key management (that monitoring is Pro).
    """
    now = int(time.time())
    note = "manual CA rotation trigger; device rotation via cmd rotate_cert (firmware EST, HC-6)"
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO cert_rotations (requested_at, status, note) VALUES (?, ?, ?)",
            (now, "triggered", note),
        )
        conn.commit()
        rotation_id = cur.lastrowid
    finally:
        conn.close()
    return ok({"id": rotation_id, "status": "triggered", "requested_at": now, "note": note})
