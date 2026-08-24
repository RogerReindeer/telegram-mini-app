from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..assets import static_manifest
from ..cache import cache_stats
from ..config import settings
from ..security import (
    ADMIN_COOKIE_NAME,
    admin_request_is_authorized,
    constant_time_equals,
    make_admin_session_token,
    read_limited_body,
)
from ..services.diagnostics import build_content_audit
from ..services.analytics import build_analytics_summary
from ..services.production import build_production_report


def create_admin_page_router(*, templates: Jinja2Templates, app_title: str) -> APIRouter:
    router = APIRouter()

    @router.get("/admin/login")
    def admin_login_page(request: Request, error: str = ""):
        if admin_request_is_authorized(request):
            return RedirectResponse("/admin", status_code=303)
        return templates.TemplateResponse(request, "admin_login.html", {
            "app_title": app_title,
            "error": bool(error),
        })

    @router.post("/admin/login")
    async def admin_login(request: Request):
        body = await read_limited_body(request, max_bytes=4096)
        form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
        token = str((form.get("token") or [""])[0]).strip()
        if not settings.admin_token or not constant_time_equals(token, settings.admin_token):
            return RedirectResponse("/admin/login?error=1", status_code=303)
        response = RedirectResponse("/admin", status_code=303)
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            make_admin_session_token(),
            httponly=True,
            secure=settings.app_env == "production",
            samesite="lax",
            max_age=max(300, int(settings.admin_session_ttl_seconds or 43200)),
            path="/",
        )
        return response

    @router.post("/admin/logout")
    def admin_logout():
        response = RedirectResponse("/admin/login", status_code=303)
        response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
        return response

    @router.get("/admin")
    def admin_page(request: Request):
        if not admin_request_is_authorized(request):
            return RedirectResponse("/admin/login", status_code=303)
        audit = build_content_audit()
        production = build_production_report()
        analytics = build_analytics_summary(days=30)
        version = {"version": production.get("app_version", ""), "environment": settings.app_env, "assets": static_manifest()}
        return templates.TemplateResponse(request, "admin.html", {
            "app_title": app_title,
            "audit": audit,
            "production": production,
            "cache": cache_stats(),
            "version": version,
            "analytics": analytics,
        })

    return router
