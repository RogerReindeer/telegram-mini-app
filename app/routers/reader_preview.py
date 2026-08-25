from __future__ import annotations

from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..security import (
    READER_PREVIEW_COOKIE_NAME,
    constant_time_equals,
    make_reader_preview_session_token,
    read_limited_body,
    valid_reader_preview_session_token,
)


def _safe_next(value: str) -> str:
    target = (value or "/library").strip()
    if not target.startswith("/") or target.startswith("//"):
        return "/library"
    if target.startswith(("/library", "/novel/", "/chapter/")):
        return target
    return "/library"


def create_reader_preview_router(*, templates: Jinja2Templates, app_title: str) -> APIRouter:
    router = APIRouter()

    @router.get("/reader-preview")
    def reader_preview_page(request: Request, next: str = "/library", error: str = ""):
        if valid_reader_preview_session_token(request.cookies.get(READER_PREVIEW_COOKIE_NAME, "")):
            return RedirectResponse(_safe_next(next), status_code=303)
        return templates.TemplateResponse(request, "reader_preview.html", {
            "app_title": app_title,
            "next_path": _safe_next(next),
            "error": bool(error),
            "configured": bool(settings.reader_preview_token),
        })

    @router.post("/reader-preview/login")
    async def reader_preview_login(request: Request):
        body = await read_limited_body(request, max_bytes=4096)
        form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
        token = str((form.get("token") or [""])[0]).strip()
        next_path = _safe_next(str((form.get("next") or ["/library"])[0]))
        if not settings.reader_preview_token or not constant_time_equals(token, settings.reader_preview_token):
            return RedirectResponse(f"/reader-preview?error=1&next={quote(next_path, safe='/')}", status_code=303)
        response = RedirectResponse(next_path, status_code=303)
        response.set_cookie(
            READER_PREVIEW_COOKIE_NAME,
            make_reader_preview_session_token(),
            httponly=True,
            secure=settings.app_env == "production",
            samesite="lax",
            max_age=max(300, int(settings.admin_session_ttl_seconds or 43200)),
            path="/",
        )
        return response

    @router.post("/reader-preview/logout")
    def reader_preview_logout():
        response = RedirectResponse("/reader-preview", status_code=303)
        response.delete_cookie(READER_PREVIEW_COOKIE_NAME, path="/")
        return response

    return router
