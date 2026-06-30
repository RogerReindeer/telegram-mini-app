from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from ..assets import static_manifest
from ..cache import cache_stats
from ..security import require_sync_token
from ..services.diagnostics import build_content_audit
from ..services.production import build_production_report


def create_admin_page_router(*, templates: Jinja2Templates, app_title: str) -> APIRouter:
    router = APIRouter()

    @router.get("/admin")
    def admin_page(request: Request, token: str = ""):
        require_sync_token(request, token)
        audit = build_content_audit()
        production = build_production_report()
        version = {"version": production.get("app_version", ""), "environment": "production", "assets": static_manifest()}
        return templates.TemplateResponse(request, "admin.html", {
            "app_title": app_title,
            "token": token,
            "audit": audit,
            "production": production,
            "cache": cache_stats(),
            "version": version,
        })

    return router
