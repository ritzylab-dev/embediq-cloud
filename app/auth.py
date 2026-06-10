# app/auth.py — single-admin login, JWT, and device validation for the broker plugin
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hmac
import os
import time
from typing import Any

import bcrypt
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from app.config import get_internal_api_key, get_settings
from app.db import get_connection
from app.envelope import ok

TOKEN_TTL_SECONDS = 24 * 60 * 60

# --- device-auth rate limit (in-process sliding window; the /internal/auth brute-force guard) ---
_RATE_WINDOW_SECONDS = 60
_RATE_MAX_FAILURES = 10
_auth_failures: dict[str, list[float]] = {}


def reset_rate_limit() -> None:
    """Clear the throttle state (used by tests)."""
    _auth_failures.clear()


def _is_throttled(source: str) -> bool:
    cutoff = time.time() - _RATE_WINDOW_SECONDS
    recent = [t for t in _auth_failures.get(source, []) if t >= cutoff]
    _auth_failures[source] = recent
    return len(recent) >= _RATE_MAX_FAILURES


def _record_auth_failure(source: str) -> None:
    _auth_failures.setdefault(source, []).append(time.time())


def require_internal_key(
    x_internal_key: str | None = Header(default=None),
    user_agent: str | None = Header(default=None),
) -> None:
    """Guard the public /internal/* endpoints with the shared secret when one is configured.

    Enforced only when INTERNAL_API_KEY is set (dev/CI may leave it empty). The secret may
    arrive via `X-Internal-Key` (direct callers, e.g. the e2e) or `User-Agent` (the go-auth
    broker, which has no custom-header facility in v3.0.0 — see mosquitto.prod.conf).
    Constant-time comparison. These headers carry the secret and must never be logged (R-8).
    """
    key = get_internal_api_key()
    if not key:
        return
    presented = [value for value in (x_internal_key, user_agent) if value]
    if not any(hmac.compare_digest(value, key) for value in presented):
        raise HTTPException(status_code=401, detail="missing or invalid internal key")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(sub: str, secret: str) -> str:
    payload = {"sub": sub, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict[str, Any]:
    return jwt.decode(token, secret, algorithms=["HS256"])


def require_admin(authorization: str | None = Header(default=None)) -> str:
    """Validate the admin Bearer JWT. Used as a router-level dependency."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token, get_settings().JWT_SECRET)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="invalid token subject")
    return sub


class LoginRequest(BaseModel):
    username: str
    password: str


class InternalAuthRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    cert_cn: str | None = None


class InternalAclRequest(BaseModel):
    username: str | None = None
    topic: str | None = None
    acc: int | None = None
    clientid: str | None = None


# The EmbedIQ MQTT namespace; the broker plugin authorizes only topics under it.
TOPIC_NAMESPACE = "embediq/"


def _bridge_credential_ok(username: str | None, password: str | None) -> bool:
    """The consumer bridge authenticates with an internal credential in the prod profile
    (where the broker is non-anonymous). Disabled unless both env vars are set."""
    bridge_user = os.environ.get("INTERNAL_BRIDGE_USER")
    bridge_pass = os.environ.get("INTERNAL_BRIDGE_PASS")
    return bool(bridge_user and bridge_pass and username == bridge_user and password == bridge_pass)


auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
internal_router = APIRouter(prefix="/internal", tags=["internal"])


@auth_router.post("/login")
def login(body: LoginRequest) -> dict[str, Any]:
    settings = get_settings()
    if body.username != settings.ADMIN_USER or not verify_password(
        body.password, settings.ADMIN_PASS_HASH
    ):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return ok({"token": create_token(settings.ADMIN_USER, settings.JWT_SECRET)})


@internal_router.post("/auth", dependencies=[Depends(require_internal_key)])
def internal_auth(body: InternalAuthRequest, request: Request) -> dict[str, Any]:
    """Validate a *device* (not a user) for the Mosquitto auth plugin (wired in PR-B3).

    Public (no admin JWT), side-effect-free: cert_cn match, or device-id + bcrypt password.
    The consumer bridge may authenticate with its internal credential (prod profile).
    Password failures are rate-limited per source so this is not an open brute-force oracle.
    """
    source = request.client.host if request.client else "unknown"
    if _is_throttled(source):
        raise HTTPException(status_code=429, detail="too many authentication failures; slow down")
    if _bridge_credential_ok(body.username, body.password):
        return ok({"result": "allow"})
    conn = get_connection()
    try:
        if body.cert_cn:
            row = conn.execute(
                "SELECT 1 FROM devices WHERE cert_cn = ?", (body.cert_cn,)
            ).fetchone()
            if row is not None:
                return ok({"result": "allow"})
        if body.username and body.password:
            row = conn.execute(
                "SELECT password_hash FROM devices WHERE id = ?", (body.username,)
            ).fetchone()
            if (
                row is not None
                and row["password_hash"]
                and verify_password(body.password, row["password_hash"])
            ):
                return ok({"result": "allow"})
    finally:
        conn.close()
    _record_auth_failure(source)
    raise HTTPException(status_code=403, detail="device validation failed")


@internal_router.post("/acl", dependencies=[Depends(require_internal_key)])
def internal_acl(body: InternalAclRequest) -> dict[str, Any]:
    """Authorize a topic for the Mosquitto auth plugin (called per pub/sub in the prod profile).

    Public (no admin JWT), side-effect-free. Namespace-scoped: an authenticated client may
    read/write only under the `embediq/` topic tree (matches the broker ACL posture). Per-device
    subtree isolation is a later tightening; the bridge needs the whole namespace to consume.
    """
    topic = body.topic or ""
    if topic == "embediq" or topic.startswith(TOPIC_NAMESPACE):
        return ok({"result": "allow"})
    raise HTTPException(status_code=403, detail="topic not permitted")
