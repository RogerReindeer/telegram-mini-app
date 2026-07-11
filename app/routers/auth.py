from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..config import settings
from ..services.auth import AUTH_COOKIE_NAME, authenticate_telegram_viewer, make_session_token, viewer_access_profile, viewer_from_request

SESSION_COOKIE = AUTH_COOKIE_NAME


def create_auth_router() -> APIRouter:
    router = APIRouter(prefix="/api/auth")

    @router.get("/me")
    def me(request: Request):
        viewer = viewer_from_request(request)
        return {"viewer": viewer, "access": viewer_access_profile(viewer)}

    @router.post("/telegram")
    async def telegram(request: Request, response: Response):
        payload = await request.json()
        viewer = authenticate_telegram_viewer(str(payload.get("init_data") or ""))
        response.set_cookie(SESSION_COOKIE, make_session_token(viewer), httponly=True, secure=True, samesite="none")
        return {"status": "ok", "viewer": viewer}

    @router.post("/logout")
    def logout(response: Response):
        response.delete_cookie(SESSION_COOKIE)
        return {"status": "ok"}

    @router.get("/debug")
    def debug(request: Request, refresh: bool = False):
        viewer = viewer_from_request(request)
        profile = viewer_access_profile(viewer, force_group_refresh=refresh)
        groups = profile.get("groups") or {}
        subscriptions = profile.get("tribute_subscriptions") or []
        entitlements = profile.get("book_entitlements") or []
        role = profile.get("role") or "guest"
        rights = {
            "role": role,
            "group_role": profile.get("group_role") or "guest",
            "tribute_role": profile.get("tribute_role") or "guest",
            "can_view_gift_books": role in {"traveler", "keeper"},
            "can_read_premium_releases": role == "keeper",
            "book_entitlements_count": len(entitlements),
            "full_book_novel_ids": [
                item.get("novel_id")
                for item in entitlements
                if item.get("access_type") == "full_book" and item.get("novel_id") is not None
            ],
            "has_full_book_access": bool(profile.get("has_full_book_access")),
        }
        return {
            "viewer": viewer,
            "telegram": viewer,
            "rights": rights,
            "groups": groups,
            "tribute_subscriptions": subscriptions,
            "book_entitlements": entitlements,
            "configuration": {
                "traveler": {
                    "label": "🌱 Странствующий читатель",
                    "chat_id": settings.traveler_chat_id,
                    "normalized_chat_id": settings.normalized_traveler_chat_id,
                    "chat_ids": list(settings.traveler_chat_ids),
                    "payment_url": settings.tribute_traveler_url,
                },
                "keeper": {
                    "label": "📜 Хранитель свитков",
                    "chat_id": settings.keeper_chat_id,
                    "normalized_chat_id": settings.normalized_keeper_chat_id,
                    "chat_ids": list(settings.keeper_chat_ids),
                    "payment_url": settings.tribute_keeper_url,
                },
            },
            "checked_at": profile.get("checked_at"),
            "refresh": refresh,
        }

    return router
