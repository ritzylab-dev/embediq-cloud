# tests/test_ui.py — admin UI page-route + design-system rendering tests (PR-UI1)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""The UI ships server-rendered page shells; data is fetched client-side with the admin Bearer
JWT. These tests assert the shells render in the new design-system app shell (sidebar + topbar),
that Bootstrap is gone, and that the Overview dashboard carries its widgets. They do not exercise
the (vanilla) JS."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# The five pages that extend the app shell (login is standalone).
SHELL_PAGES = ["/ui/overview", "/ui/fleet", "/ui/devices/sensor-007", "/ui/ota", "/ui/settings"]


def test_root_redirects_to_overview(client: TestClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/ui/overview"


def test_login_page_renders(client: TestClient) -> None:
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "EmbedIQ" in body
    assert 'id="login-form"' in body
    assert 'type="password"' in body


def test_overview_page_renders(client: TestClient) -> None:
    resp = client.get("/ui/overview")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "Overview" in body
    # the 4 KPI stat cards
    assert 'id="kpi-total"' in body
    assert 'id="kpi-online"' in body
    assert 'id="kpi-attention"' in body
    assert 'id="kpi-firmware"' in body
    # the two chart canvases
    assert 'id="chart-online"' in body
    assert 'id="chart-firmware"' in body
    assert "<canvas" in body
    # needs-attention list + recent OTA / activity
    assert 'id="needs-attention"' in body
    assert 'id="recent-ota"' in body


def test_fleet_page_renders(client: TestClient) -> None:
    body = client.get("/ui/fleet").text
    assert "Fleet" in body
    assert 'id="device-table"' in body
    # UI2: the fleet-health KPI strip (reuses the .stat component) + skeleton rows
    assert 'id="fleet-health"' in body
    assert 'id="fleet-kpi-total"' in body
    assert 'id="fleet-kpi-online"' in body
    assert 'id="fleet-kpi-attention"' in body
    assert "stat-value" in body
    assert "skeleton" in body


def test_device_detail_page_renders_with_id(client: TestClient) -> None:
    resp = client.get("/ui/devices/sensor-007")
    assert resp.status_code == 200
    body = resp.text
    # the device id is injected server-side so the page's JS knows which device to fetch
    assert "sensor-007" in body
    assert 'id="device-detail"' in body
    # UI2: telemetry chart card (designed empty state under dev.sh), shadow + OTA-status cards
    assert 'id="chart-telemetry"' in body
    assert "<canvas" in body
    assert 'id="device-shadow"' in body
    assert 'id="device-ota-status"' in body


def test_device_detail_has_commands_section(client: TestClient) -> None:
    body = client.get("/ui/devices/sensor-007").text
    assert 'id="device-commands"' in body
    assert 'data-cmd="reboot"' in body
    assert 'data-cmd="rotate_cert"' in body
    assert 'data-cmd="ota_check"' in body


def test_ota_page_renders(client: TestClient) -> None:
    body = client.get("/ui/ota").text
    assert "OTA" in body
    assert 'id="firmware-upload-form"' in body
    assert 'id="firmware-table"' in body
    assert 'id="ota-status-table"' in body
    # UI2: the upload drop-zone card
    assert "dropzone" in body


def test_settings_page_renders(client: TestClient) -> None:
    body = client.get("/ui/settings").text
    assert "Settings" in body
    assert 'id="ca-cert"' in body
    assert 'id="system-health"' in body
    assert "install.sh" in body
    # UI2: design-system cards
    assert "card-head" in body


@pytest.mark.parametrize("path", SHELL_PAGES)
def test_pages_use_the_app_shell_and_design_system(client: TestClient, path: str) -> None:
    body = client.get(path).text
    assert "/static/design-system.css" in body  # the hand-authored system is linked
    assert 'class="sidebar"' in body  # left sidebar app shell
    assert 'href="/ui/overview"' in body  # sidebar nav to Overview
    assert 'id="theme-toggle"' in body  # the dark/light toggle is present
    assert 'data-theme="light"' in body  # theme driven by data-theme on <html>
    assert 'name="viewport"' in body  # mobile-responsive meta
    assert "JetBrains+Mono" in body  # brand fonts via Google Fonts CDN


@pytest.mark.parametrize("path", [*SHELL_PAGES, "/login"])
def test_pages_have_no_bootstrap(client: TestClient, path: str) -> None:
    body = client.get(path).text.lower()
    assert "bootstrap" not in body


def test_chartjs_pinned_with_sri(client: TestClient) -> None:
    body = client.get("/ui/overview").text
    assert "cdn.jsdelivr.net/npm/chart.js@4.5.1" in body  # exact version, never @latest
    assert "@latest" not in body
    assert "integrity=" in body
    assert "sha384-" in body


def test_design_system_css_is_served(client: TestClient) -> None:
    resp = client.get("/static/design-system.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]
    assert "--blue" in resp.text  # the brand tokens are present


def test_health_unchanged(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_json_api_still_protected(client: TestClient) -> None:
    # the page shells are public; the JSON API behind them stays behind require_admin
    assert client.get("/api/v1/devices").status_code == 401
