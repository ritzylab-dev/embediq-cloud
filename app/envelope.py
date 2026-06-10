# app/envelope.py — the standard API response envelope (R-7)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

# Map the standard HTTP codes (200/201/400/401/404/409/500) to stable error codes.
STATUS_CODE: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    500: "internal_error",
    502: "bad_gateway",
}


def ok(data: Any) -> dict[str, Any]:
    return {"data": data, "error": None}


def error_body(status: int, message: str) -> dict[str, Any]:
    return {"data": None, "error": {"code": STATUS_CODE.get(status, "error"), "message": message}}
