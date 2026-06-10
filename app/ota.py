# app/ota.py — OTA: Hawkbit REST proxy + non-retained cmd relay + admin device commands
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app import hawkbit, mqtt_pub
from app.auth import require_admin, require_internal_key
from app.db import get_connection
from app.envelope import ok
from app.hawkbit import HawkbitError

VALID_CMDS = {"reboot", "rotate_cert", "ota_check"}

router = APIRouter(prefix="/api/v1", tags=["ota"], dependencies=[Depends(require_admin)])
# Same shared-secret guard as the other /internal/* endpoints (constant-time, X-Internal-Key
# or User-Agent), enforced when INTERNAL_API_KEY is set.
callback_router = APIRouter(
    prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal_key)]
)


def _hawkbit_http_error(exc: HawkbitError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


class DeployRequest(BaseModel):
    firmware_id: int
    device_id: str | None = None
    group_id: str | None = None
    notes: str | None = None


class CmdRequest(BaseModel):
    cmd: str
    params: dict[str, Any] = {}


class HawkbitCallback(BaseModel):
    device_id: str
    firmware_id: int | None = None
    url: str | None = None
    checksum: str | None = None
    version: str | None = None


# --- Hawkbit REST proxy ---


@router.get("/ota/firmware")
def list_firmware() -> dict[str, Any]:
    try:
        return ok(hawkbit.list_software_modules())
    except HawkbitError as exc:
        raise _hawkbit_http_error(exc) from exc


@router.post("/ota/firmware", status_code=201)
async def post_firmware(
    name: Annotated[str, Form()],
    version: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    content = await file.read()
    try:
        module = hawkbit.create_software_module(name, version)
        hawkbit.upload_artifact(module["id"], file.filename or "artifact.bin", content)
    except HawkbitError as exc:
        raise _hawkbit_http_error(exc) from exc
    return ok({"id": module["id"], "name": name, "version": version})


@router.delete("/ota/firmware/{module_id}")
def delete_firmware(module_id: int) -> dict[str, Any]:
    try:
        hawkbit.delete_software_module(module_id)
    except HawkbitError as exc:
        raise _hawkbit_http_error(exc) from exc
    return ok({"id": module_id})


@router.post("/ota/deploy")
def deploy(body: DeployRequest) -> dict[str, Any]:
    try:
        return ok(hawkbit.create_deployment(body.firmware_id, body.device_id, body.group_id))
    except HawkbitError as exc:
        raise _hawkbit_http_error(exc) from exc


@router.get("/ota/status/{device_id}")
def ota_status(device_id: str) -> dict[str, Any]:
    try:
        return ok(hawkbit.deployment_status(device_id))
    except HawkbitError as exc:
        raise _hawkbit_http_error(exc) from exc


# --- admin device command (publishes to cmd, NOT retained) ---


@router.post("/devices/{device_id}/cmd")
def device_cmd(device_id: str, body: CmdRequest) -> dict[str, Any]:
    if body.cmd not in VALID_CMDS:
        raise HTTPException(status_code=400, detail=f"invalid cmd: {body.cmd}")
    conn = get_connection()
    try:
        exists = conn.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,)).fetchone()
    finally:
        conn.close()
    if exists is None:
        raise HTTPException(status_code=404, detail="device not found")
    mqtt_pub.publish(f"embediq/{device_id}/cmd", {"cmd": body.cmd, **body.params}, retain=False)
    return ok({"published": True})


# --- Hawkbit deployment-ready webhook → relay ota_check to cmd (NOT retained) ---


@callback_router.post("/hawkbit-callback")
def hawkbit_callback(body: HawkbitCallback) -> dict[str, Any]:
    payload = {
        "cmd": "ota_check",
        "firmware_id": body.firmware_id,
        "url": body.url,
        "checksum": body.checksum,
        "version": body.version,
    }
    mqtt_pub.publish(f"embediq/{body.device_id}/cmd", payload, retain=False)
    return ok({"relayed": True})
