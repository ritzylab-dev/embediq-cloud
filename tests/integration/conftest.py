# tests/integration/conftest.py — config + fixtures for the live-stack e2e harness
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""Fixtures that point the e2e suite at the running docker compose stack.

Every endpoint is configurable via the environment (the CI ``integration`` job sets them);
the defaults match the compose stack reachable from the host: the API and Mosquitto are
published by the base compose, InfluxDB is published by ``docker-compose.integration.yml``.
These tests talk to real services over the network — they never import ``app`` in-process.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import httpx
import pytest

# Mark the whole package ``integration`` so the unit run (``-m "not integration"``) skips it.
pytestmark = pytest.mark.integration


class StackConfig:
    """Resolved endpoints + credentials for the live stack, read from the environment."""

    def __init__(self) -> None:
        self.api_base = os.environ.get("API_BASE_URL", "http://localhost:8080")
        self.mqtt_host = os.environ.get("MQTT_HOST", "localhost")
        self.mqtt_port = int(os.environ.get("MQTT_PORT", "1883"))
        self.influx_url = os.environ.get("INFLUX_URL", "http://localhost:8086")
        self.influx_token = os.environ.get("INFLUX_TOKEN", "changeme-influx-token")
        self.influx_org = os.environ.get("INFLUX_ORG", "embediq")
        self.influx_bucket = os.environ.get("INFLUX_BUCKET", "telemetry")
        self.admin_user = os.environ.get("INTEGRATION_ADMIN_USER", "admin")
        self.admin_pass = os.environ.get("INTEGRATION_ADMIN_PASS", "integration-pass")
        # Shared secret for the public /internal/* endpoints (PR-SEC2). When set, the e2e must
        # present it as X-Internal-Key, exercising the enforced path that CI runs with.
        self.internal_key = os.environ.get("INTERNAL_API_KEY", "")


def internal_headers(cfg: StackConfig) -> dict[str, str]:
    """Header carrying the /internal shared secret (empty dict when enforcement is off)."""
    return {"X-Internal-Key": cfg.internal_key} if cfg.internal_key else {}


@pytest.fixture(scope="session")
def cfg() -> StackConfig:
    return StackConfig()


@pytest.fixture(scope="session")
def api_ready(cfg: StackConfig) -> StackConfig:
    """Wait for the API ``/health`` to answer 200 before any test runs."""
    deadline = time.monotonic() + 60
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{cfg.api_base}/health", timeout=5)
            if resp.status_code == 200:
                return cfg
        except httpx.HTTPError as exc:  # not up yet
            last_exc = exc
        time.sleep(2)
    raise RuntimeError(f"API never became healthy at {cfg.api_base} ({last_exc})")


@pytest.fixture
def auth_headers(api_ready: StackConfig) -> dict[str, str]:
    """Log in as the single admin and return the Bearer header."""
    resp = httpx.post(
        f"{api_ready.api_base}/api/v1/auth/login",
        json={"username": api_ready.admin_user, "password": api_ready.admin_pass},
        timeout=10,
    )
    assert resp.status_code == 200, f"admin login failed: {resp.status_code} {resp.text}"
    token = resp.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def api(api_ready: StackConfig) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=api_ready.api_base, timeout=15) as client:
        yield client


def influx_count(cfg: StackConfig, device_id: str, *, timeout: float = 30.0) -> int:
    """Poll the InfluxDB query API until ``telemetry`` points for ``device_id`` appear.

    Returns the number of matching rows (0 if none within ``timeout``). Uses the v2 Flux
    query API over the published InfluxDB port.
    """
    flux = (
        f'from(bucket:"{cfg.influx_bucket}") '
        "|> range(start:-1h) "
        '|> filter(fn:(r) => r._measurement == "telemetry") '
        f'|> filter(fn:(r) => r.device_id == "{device_id}")'
    )
    headers = {
        "Authorization": f"Token {cfg.influx_token}",
        "Content-Type": "application/vnd.flux",
        "Accept": "application/csv",
    }
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.post(
                f"{cfg.influx_url}/api/v2/query",
                params={"org": cfg.influx_org},
                content=flux,
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                # Annotated-CSV: data rows for a result table begin with ",_result";
                # annotation/header rows begin with "#" or ",result". Count only data rows.
                data_rows = [line for line in resp.text.splitlines() if line.startswith(",_result")]
                if data_rows:
                    return len(data_rows)
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return 0
