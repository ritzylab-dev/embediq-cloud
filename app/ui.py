# app/ui.py — server-rendered admin UI page shells (overview, fleet, device, OTA, settings)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""The admin UI is server-rendered page shells (Jinja2 + a hand-authored design system, vanilla
ES — no build step, R-1). These routes are intentionally PUBLIC: they return only static HTML
chrome. The data is fetched client-side from the JSON API (which stays behind require_admin)
using the admin Bearer JWT held in sessionStorage; a missing/expired token redirects to /login
in JS. "/" redirects to the Overview dashboard, the post-login landing page.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["ui"])


@router.get("/")
def root() -> RedirectResponse:
    # The Overview dashboard is the post-login landing page; "/" redirects to it.
    # The page shell is public; its JS redirects to /login when no token is held.
    return RedirectResponse(url="/ui/overview", status_code=307)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html")


@router.get("/ui/overview", response_class=HTMLResponse)
def overview_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "overview.html", {"active": "overview"})


@router.get("/ui/fleet", response_class=HTMLResponse)
def fleet_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "fleet.html", {"active": "fleet"})


@router.get("/ui/devices/{device_id}", response_class=HTMLResponse)
def device_page(request: Request, device_id: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "device.html", {"device_id": device_id, "active": "fleet"}
    )


@router.get("/ui/ota", response_class=HTMLResponse)
def ota_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "ota.html", {"active": "ota"})


@router.get("/ui/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings.html", {"active": "settings"})
