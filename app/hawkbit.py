# app/hawkbit.py — thin Hawkbit REST client (we proxy; Hawkbit owns all OTA logic, R: no OTA logic)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_hawkbit_settings

log = logging.getLogger("embediq.hawkbit")

TIMEOUT = 10.0


class HawkbitError(Exception):
    """A Hawkbit call failed. `status_code` maps to the API envelope code (502/404/409)."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    settings = get_hawkbit_settings()
    url = settings.HAWKBIT_URL.rstrip("/") + path
    try:
        resp = httpx.request(
            method,
            url,
            auth=(settings.HAWKBIT_USER, settings.HAWKBIT_ADMIN_PASS),
            timeout=TIMEOUT,
            **kwargs,
        )
    except httpx.HTTPError as exc:
        raise HawkbitError(502, f"hawkbit unreachable: {exc}") from exc
    if resp.status_code >= 400:
        raise HawkbitError(resp.status_code, f"hawkbit returned {resp.status_code}")
    return resp


def list_software_modules() -> list[dict[str, Any]]:
    content = _request("GET", "/rest/v1/softwaremodules").json().get("content", [])
    return [
        {
            "id": m["id"],
            "name": m["name"],
            "version": m["version"],
            "size_bytes": m.get("size", 0),
            "created_at": m.get("createdAt"),
        }
        for m in content
    ]


def create_software_module(name: str, version: str) -> dict[str, Any]:
    body = [{"name": name, "version": version, "type": "os"}]
    created = _request("POST", "/rest/v1/softwaremodules", json=body).json()
    module: dict[str, Any] = created[0] if isinstance(created, list) else created
    return module


def upload_artifact(module_id: int, filename: str, content: bytes) -> None:
    _request(
        "POST",
        f"/rest/v1/softwaremodules/{module_id}/artifacts",
        files={"file": (filename, content)},
    )


def delete_software_module(module_id: int) -> None:
    _request("DELETE", f"/rest/v1/softwaremodules/{module_id}")


def create_deployment(
    firmware_id: int, device_id: str | None = None, group_id: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"firmware_id": firmware_id}
    if device_id is not None:
        body["device_id"] = device_id
    if group_id is not None:
        body["group_id"] = group_id
    result: dict[str, Any] = _request("POST", "/rest/v1/deployments", json=body).json()
    return result


def deployment_status(device_id: str) -> dict[str, Any]:
    data = _request("GET", f"/rest/v1/targets/{device_id}").json()
    return {
        "status": data.get("updateStatus", "unknown"),
        "progress_pct": data.get("progress", 0),
        "version": data.get("installedVersion"),
        "updated_at": data.get("lastModifiedAt"),
    }


def mark_finished(device_id: str) -> None:
    """Best-effort: tell Hawkbit the deployment succeeded. Never raises into the caller."""
    try:
        _request(
            "POST",
            f"/rest/v1/targets/{device_id}/actions/feedback",
            json={"status": {"execution": "closed", "result": {"finished": "success"}}},
        )
    except HawkbitError as exc:
        log.warning("hawkbit mark_finished failed for %s: %s", device_id, exc)


def mark_failed(device_id: str, reason: str) -> None:
    """Best-effort: tell Hawkbit the deployment failed. Never raises into the caller."""
    try:
        _request(
            "POST",
            f"/rest/v1/targets/{device_id}/actions/feedback",
            json={
                "status": {
                    "execution": "closed",
                    "result": {"finished": "failure"},
                    "details": [reason],
                }
            },
        )
    except HawkbitError as exc:
        log.warning("hawkbit mark_failed failed for %s: %s", device_id, exc)
