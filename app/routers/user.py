from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request

from ..schemas import ResetProgressPayload, SaveLibraryPayload, SaveProgressPayload
from ..services.user_state import get_user_state_rows, reset_user_progress, save_user_library, save_user_progress


def create_user_router(require_authenticated_viewer: Callable, public_viewer: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/user")

    def user_id(request: Request) -> int:
        viewer = require_authenticated_viewer(request)
        return int(viewer.get("user_id") or viewer.get("telegram_user_id") or 0)

    @router.get("/state")
    def state(request: Request):
        return get_user_state_rows(user_id(request))

    @router.get("/history")
    def history(request: Request):
        return get_user_state_rows(user_id(request)).get("history", [])

    @router.put("/progress")
    def progress(request: Request, payload: SaveProgressPayload):
        return save_user_progress(user_id(request), payload.to_service_dict())

    @router.post("/progress/reset")
    def reset_progress(request: Request, payload: ResetProgressPayload):
        return reset_user_progress(user_id(request), payload.to_service_dict())

    @router.put("/library")
    def library(request: Request, payload: SaveLibraryPayload):
        return save_user_library(user_id(request), payload.to_service_dict())

    return router
