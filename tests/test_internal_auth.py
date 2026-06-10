# tests/test_internal_auth.py — device validation for the Mosquitto plugin (PR-B3)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

Headers = dict[str, str]


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> None:
    """Clear the in-process device-auth throttle so failures don't leak across tests."""
    from app import auth

    auth.reset_rate_limit()


def test_internal_auth_valid_password_200(client: TestClient, auth_headers: Headers) -> None:
    client.post(
        "/api/v1/devices", headers=auth_headers, json={"id": "dev-1", "password": "devpass"}
    )
    resp = client.post("/internal/auth", json={"username": "dev-1", "password": "devpass"})
    assert resp.status_code == 200


def test_internal_auth_wrong_password_403(client: TestClient, auth_headers: Headers) -> None:
    client.post(
        "/api/v1/devices", headers=auth_headers, json={"id": "dev-1", "password": "devpass"}
    )
    resp = client.post("/internal/auth", json={"username": "dev-1", "password": "nope"})
    assert resp.status_code == 403


def test_internal_auth_valid_cert_cn_200(client: TestClient, auth_headers: Headers) -> None:
    client.post(
        "/api/v1/devices", headers=auth_headers, json={"id": "dev-1", "cert_cn": "device-cn-1"}
    )
    resp = client.post("/internal/auth", json={"cert_cn": "device-cn-1"})
    assert resp.status_code == 200


def test_internal_auth_unknown_device_403(client: TestClient) -> None:
    assert (
        client.post("/internal/auth", json={"username": "ghost", "password": "x"}).status_code
        == 403
    )
    assert client.post("/internal/auth", json={"cert_cn": "ghost-cn"}).status_code == 403


def test_internal_auth_not_behind_admin_jwt(client: TestClient) -> None:
    # No Authorization header at all — the endpoint must still answer (deny), not 401.
    assert client.post("/internal/auth", json={"cert_cn": "ghost"}).status_code == 403


# --- bridge internal credential (env-gated; lets the consumer bridge auth in prod) ---


def test_internal_auth_bridge_credential(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERNAL_BRIDGE_USER", "_bridge")
    monkeypatch.setenv("INTERNAL_BRIDGE_PASS", "bridgepass")
    ok_resp = client.post("/internal/auth", json={"username": "_bridge", "password": "bridgepass"})
    assert ok_resp.status_code == 200
    bad_resp = client.post("/internal/auth", json={"username": "_bridge", "password": "wrong"})
    assert bad_resp.status_code == 403


def test_internal_auth_bridge_disabled_when_unset(client: TestClient) -> None:
    # With no bridge env configured, the bridge name is just an unknown device → denied.
    assert (
        client.post("/internal/auth", json={"username": "_bridge", "password": "x"}).status_code
        == 403
    )


# --- ACL check (the plugin's authorization call: namespace-scoped) ---


def test_internal_acl_allows_embediq_namespace(client: TestClient) -> None:
    resp = client.post(
        "/internal/acl",
        json={"username": "dev-1", "topic": "embediq/dev-1/telemetry", "acc": 2, "clientid": "c"},
    )
    assert resp.status_code == 200


def test_internal_acl_denies_foreign_namespace(client: TestClient) -> None:
    resp = client.post(
        "/internal/acl",
        json={"username": "dev-1", "topic": "secret/topic", "acc": 1, "clientid": "c"},
    )
    assert resp.status_code == 403


def test_internal_acl_not_behind_admin_jwt(client: TestClient) -> None:
    # public, like /internal/auth — answers allow/deny, never 401 (when no shared key is set)
    assert (
        client.post(
            "/internal/acl", json={"username": "x", "topic": "embediq/x", "acc": 1}
        ).status_code
        == 200
    )


# --- shared-secret enforcement on /internal/* (safe-by-default; PR-SEC2) ---


def test_internal_auth_401_without_key_when_required(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "s3kret")
    resp = client.post("/internal/auth", json={"username": "dev-1", "password": "devpass"})
    assert resp.status_code == 401


def test_internal_auth_200_with_x_internal_key(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "s3kret")
    client.post(
        "/api/v1/devices", headers=auth_headers, json={"id": "dev-1", "password": "devpass"}
    )
    resp = client.post(
        "/internal/auth",
        json={"username": "dev-1", "password": "devpass"},
        headers={"X-Internal-Key": "s3kret"},
    )
    assert resp.status_code == 200


def test_internal_auth_200_with_user_agent_key(
    client: TestClient, auth_headers: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the broker (go-auth) carries the secret in User-Agent
    monkeypatch.setenv("INTERNAL_API_KEY", "s3kret")
    client.post(
        "/api/v1/devices", headers=auth_headers, json={"id": "dev-1", "password": "devpass"}
    )
    resp = client.post(
        "/internal/auth",
        json={"username": "dev-1", "password": "devpass"},
        headers={"User-Agent": "s3kret"},
    )
    assert resp.status_code == 200


def test_internal_auth_401_wrong_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "s3kret")
    resp = client.post(
        "/internal/auth",
        json={"username": "dev-1", "password": "devpass"},
        headers={"X-Internal-Key": "nope"},
    )
    assert resp.status_code == 401


def test_internal_acl_requires_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "s3kret")
    body = {"username": "dev-1", "topic": "embediq/dev-1/telemetry", "acc": 1}
    assert client.post("/internal/acl", json=body).status_code == 401
    assert (
        client.post("/internal/acl", json=body, headers={"X-Internal-Key": "s3kret"}).status_code
        == 200
    )


def test_internal_endpoints_legacy_when_key_unset(
    client: TestClient, auth_headers: Headers
) -> None:
    # No INTERNAL_API_KEY in the env (dev) → no enforcement, unchanged behaviour.
    client.post(
        "/api/v1/devices", headers=auth_headers, json={"id": "dev-1", "password": "devpass"}
    )
    assert (
        client.post("/internal/auth", json={"username": "dev-1", "password": "devpass"}).status_code
        == 200
    )


# --- rate-limit on the device-auth brute-force surface ---


def test_internal_auth_rate_limited_after_repeated_failures(
    client: TestClient, auth_headers: Headers
) -> None:
    client.post(
        "/api/v1/devices", headers=auth_headers, json={"id": "dev-1", "password": "devpass"}
    )
    statuses = [
        client.post("/internal/auth", json={"username": "dev-1", "password": "wrong"}).status_code
        for _ in range(15)
    ]
    assert 403 in statuses  # early failures are normal auth denials
    assert 429 in statuses  # the source gets throttled once it crosses the threshold


# --- fail-closed in production (config-level) ---


def test_prod_profile_requires_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setenv("EMBEDIQ_PROFILE", "prod")
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.assert_internal_key_in_prod()
    monkeypatch.setenv("INTERNAL_API_KEY", "s3kret")
    config.assert_internal_key_in_prod()  # set → no error


def test_dev_profile_allows_empty_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setenv("EMBEDIQ_PROFILE", "dev")
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    config.assert_internal_key_in_prod()  # dev → no error
