from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..security import read_json_payload
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
        payload = await read_json_payload(request)
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
        return {"viewer": viewer, "rights": viewer_access_profile(viewer), "refresh": refresh}

    return router
