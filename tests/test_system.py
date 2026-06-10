# tests/test_system.py — system health + certs endpoints
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app import __version__
from app.db import get_connection

Headers = dict[str, str]


def _write_ca_cert(path: Path, *, days_valid: int) -> None:
    """Write a self-signed CA PEM to `path` that expires in `days_valid` days."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EmbedIQ-CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=days_valid))
        .sign(key, hashes.SHA256())
    )
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def test_system_health_shape(client: TestClient, auth_headers: Headers) -> None:
    resp = client.get("/api/v1/system/health", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "ok"
    assert data["version"] == __version__
    assert "devices_online" in data
    assert "uptime_s" in data


def test_system_certs_graceful_when_absent(client: TestClient, auth_headers: Headers) -> None:
    # No /certs/ca.crt in the test environment → graceful nulls, not a 500.
    resp = client.get("/api/v1/system/certs", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["ca_cert_pem"] is None
    assert body["data"]["expires_in_days"] is None
    assert body["data"]["warning"] is False  # no cert → nothing to warn about


def test_system_certs_warning_true_when_expiring(
    client: TestClient,
    auth_headers: Headers,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import registry

    ca = tmp_path / "ca.crt"
    _write_ca_cert(ca, days_valid=10)
    monkeypatch.setattr(registry, "CA_CERT_PATH", ca)
    monkeypatch.setenv("CERT_WARN_DAYS", "30")
    data = client.get("/api/v1/system/certs", headers=auth_headers).json()["data"]
    assert 8 <= data["expires_in_days"] <= 11
    assert data["warning"] is True
    assert data["warning_days"] == 30


def test_system_certs_warning_false_when_far(
    client: TestClient,
    auth_headers: Headers,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import registry

    ca = tmp_path / "ca.crt"
    _write_ca_cert(ca, days_valid=400)
    monkeypatch.setattr(registry, "CA_CERT_PATH", ca)
    monkeypatch.setenv("CERT_WARN_DAYS", "30")
    data = client.get("/api/v1/system/certs", headers=auth_headers).json()["data"]
    assert data["expires_in_days"] > 300
    assert data["warning"] is False


def test_certs_rotate_records_event(client: TestClient, auth_headers: Headers) -> None:
    resp = client.post("/api/v1/system/certs/rotate", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "id" in data
    assert data["status"] == "triggered"
    assert "requested_at" in data
    # the event is persisted for tracking
    conn = get_connection()
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM cert_rotations").fetchone()["n"]
    finally:
        conn.close()
    assert n == 1


def test_certs_rotate_requires_jwt(client: TestClient) -> None:
    assert client.post("/api/v1/system/certs/rotate").status_code == 401
