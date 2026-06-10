# app/main.py — FastAPI application entrypoint, routing, and envelope error handling
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__, bridge
from app.auth import auth_router, internal_router
from app.config import assert_internal_key_in_prod, get_bridge_settings
from app.db import init_db
from app.envelope import error_body
from app.ota import callback_router as ota_callback_router
from app.ota import router as ota_router
from app.registry import router as registry_router
from app.shadow import router as shadow_router
from app.ui import router as ui_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    assert_internal_key_in_prod()  # fail closed: prod requires the /internal shared secret
    init_db()
    if get_bridge_settings().BRIDGE_ENABLED:
        bridge.start_bridge()
    try:
        yield
    finally:
        bridge.stop_bridge()


app = FastAPI(title="EmbedIQ Cloud", version=__version__, lifespan=lifespan)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content=error_body(exc.status_code, str(exc.detail))
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, _exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=400, content=error_body(400, "invalid request body"))


app.include_router(auth_router)
app.include_router(internal_router)
app.include_router(registry_router)
app.include_router(shadow_router)
app.include_router(ota_router)
app.include_router(ota_callback_router)
app.include_router(ui_router)

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
