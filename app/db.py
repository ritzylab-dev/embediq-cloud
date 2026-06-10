# app/db.py — SQLite schema + connection helpers
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    cert_cn TEXT,
    password_hash TEXT,
    group_id TEXT NOT NULL DEFAULT 'default',
    attributes TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS device_state (
    device_id TEXT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
    online INTEGER NOT NULL DEFAULT 0,
    last_seen INTEGER,
    ip_address TEXT,
    firmware_version TEXT);
CREATE TABLE IF NOT EXISTS device_shadow (
    device_id TEXT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
    desired TEXT NOT NULL DEFAULT '{}',
    reported TEXT NOT NULL DEFAULT '{}',
    updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    description TEXT,
    created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS cert_rotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_at INTEGER NOT NULL,
    status TEXT NOT NULL,
    note TEXT);
"""


def db_path() -> str:
    """Resolve the SQLite file path from the environment.

    Read directly (not via Settings) so the DB layer does not require the auth
    secrets — `/health` and schema init must work even before credentials exist.
    """
    return os.environ.get("DB_PATH", "/data/embediq.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT 1 FROM groups WHERE id = 'default'").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO groups (id, description, created_at) "
                "VALUES ('default', 'Default group', ?)",
                (int(time.time()),),
            )
        conn.commit()
    finally:
        conn.close()
