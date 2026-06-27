"""Small owner-facing admin dashboard.

The JSON admin API is useful, but opening raw JSON on a phone is painful.  This
page renders the same read-only diagnostics as HTML and keeps destructive
operations behind explicit forms protected by SYNC_TOKEN.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates

from ..assets import static_manifest
from ..cache import cache_stats
from ..config import settings
from ..security import require_sync_token
from ..services.diagnostics import build_content_audit
from ..services.production import build_production_report


def create_admin_page_router(*, templates: Jinja2Templates, app_title: str) -> APIRouter:
    router = APIRouter()

    @router.get("/admin")
    async def admin_dashboard(request: Request, token: str | None = Query(default=None)):
        require_sync_token(request, token)
        audit = build_content_audit()
        production = build_production_report()
        return templates.TemplateResponse(
            "admin.html",
            {
                "request": request,
                "app_title": app_title,
                "token": token or "",
                "audit": audit,
                "production": production,
                "cache": cache_stats(),
                "version": {
                    "app": "telegram-mini-app",
                    "version": settings.app_version,
                    "environment": settings.app_env,
                    "assets": static_manifest(),
                },
            },
        )

    return router
