"""Authentication API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from ..services.events import record_event
from ..services.auth import (
    ACCESS_DEBUG_ENABLED,
    APP_ENV,
    AUTH_COOKIE_NAME,
    AUTH_SESSION_TTL_SECONDS,
    KEEPER_CHAT_ID,
    TRIBUTE_API_KEY,
    TRIBUTE_KEEPER_SUBSCRIPTION_ID,
    TRIBUTE_TRAVELER_SUBSCRIPTION_ID,
    TRAVELER_CHAT_ID,
    authenticate_telegram_viewer,
    clean_value,
    make_session_token,
    public_viewer,
    resolve_access_profile,
    viewer_from_request,
)


def create_auth_router() -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.get("/me")
    async def api_auth_me(request: Request):
        viewer = viewer_from_request(request)
        return {"status": "ok", "viewer": public_viewer(viewer)}

    @router.post("/telegram")
    async def api_auth_telegram(request: Request):
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Ожидался JSON") from exc

        init_data = str(payload.get("init_data") or payload.get("initData") or "")
        if not init_data:
            raise HTTPException(status_code=400, detail="initData отсутствует")

        viewer = authenticate_telegram_viewer(init_data)
        record_event("auth_success", role=viewer.get("role"), authenticated=viewer.get("authenticated"))
        response = JSONResponse({"status": "ok", "viewer": public_viewer(viewer)})
        response.set_cookie(
            AUTH_COOKIE_NAME,
            make_session_token(viewer),
            max_age=AUTH_SESSION_TTL_SECONDS,
            httponly=True,
            secure=APP_ENV == "production",
            samesite="lax",
            path="/",
        )
        return response

    @router.post("/logout")
    async def api_auth_logout():
        record_event("auth_logout")
        response = JSONResponse({"status": "ok"})
        response.delete_cookie(AUTH_COOKIE_NAME, path="/")
        return response

    @router.get("/debug")
    async def api_auth_debug(request: Request, refresh: bool = Query(default=False)):
        if not ACCESS_DEBUG_ENABLED:
            raise HTTPException(status_code=404, detail="Debug endpoint disabled")

        viewer = viewer_from_request(request)
        if not viewer.get("authenticated") or not viewer.get("user_id"):
            return {
                "status": "ok",
                "authenticated": False,
                "message": "Telegram initData ещё не подтверждён.",
                "telegram": {"user_id": None, "first_name": "", "username": ""},
                "rights": {
                    "role": "guest",
                    "can_read_free": True,
                    "can_read_traveler": False,
                    "can_read_keeper": False,
                },
            }

        profile = resolve_access_profile(int(viewer["user_id"]), force_group_refresh=refresh)
        role = clean_value(profile.get("role")) or "guest"
        return {
            "status": "ok",
            "authenticated": True,
            "telegram": {
                "user_id": viewer.get("user_id"),
                "first_name": viewer.get("first_name") or "",
                "username": viewer.get("username") or "",
            },
            "rights": {
                "role": role,
                "can_view_regular_books": True,
                "can_view_gift_books": role in {"traveler", "keeper"},
                "can_read_free_releases": True,
                "can_read_premium_releases": role == "keeper",
                "traveler_reads_premium": False,
                "book_entitlements_count": len(profile.get("book_entitlements") or []),
                "full_book_novel_ids": [
                    row.get("novel_id")
                    for row in (profile.get("book_entitlements") or [])
                    if clean_value(row.get("access_type")) == "full_book"
                ],
            },
            "groups": profile.get("groups") or {},
            "tribute_subscriptions": profile.get("tribute_subscriptions") or [],
            "book_entitlements": profile.get("book_entitlements") or [],
            "configuration": {
                "traveler_chat_id": TRAVELER_CHAT_ID,
                "keeper_chat_id": KEEPER_CHAT_ID,
                "tribute_traveler_subscription_id": TRIBUTE_TRAVELER_SUBSCRIPTION_ID,
                "tribute_keeper_subscription_id": TRIBUTE_KEEPER_SUBSCRIPTION_ID,
                "tribute_webhook_configured": bool(TRIBUTE_API_KEY),
            },
            "checked_at": profile.get("checked_at"),
        }

    return router
