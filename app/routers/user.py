"""User state API router.

Routes here expose the current client contract while delegating all Supabase
work to services.user_state. The router is created with auth callbacks from
application.py so Telegram session handling stays in one place for now.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..schemas import ResetProgressPayload, SaveLibraryPayload, SaveProgressPayload

from ..services.user_state import (
    ChapterNotFoundError,
    UserStateError,
    get_user_state_rows,
    reset_user_progress,
    save_user_library,
    save_user_progress,
)

ViewerFn = Callable[[Request], dict[str, Any]]
PublicViewerFn = Callable[[dict[str, Any]], dict[str, Any]]


def create_user_router(
    require_authenticated_viewer: ViewerFn,
    public_viewer: PublicViewerFn,
) -> APIRouter:
    router = APIRouter(prefix="/api/user", tags=["user-state"])

    @router.get("/state")
    async def api_user_state(request: Request):
        viewer = require_authenticated_viewer(request)
        try:
            state = get_user_state_rows(int(viewer["user_id"]))
        except Exception as error:
            print("Unable to load user state:", error)
            raise HTTPException(
                status_code=503,
                detail="Не удалось загрузить прогресс из user_novel_state и user_chapter_progress.",
            ) from error
        return {"status": "ok", "viewer": public_viewer(viewer), **state}

    @router.get("/history")
    async def api_user_history(request: Request):
        viewer = require_authenticated_viewer(request)
        try:
            state = get_user_state_rows(int(viewer["user_id"]))
        except Exception as error:
            print("Unable to load user history:", error)
            raise HTTPException(
                status_code=503,
                detail="Не удалось загрузить историю чтения.",
            ) from error
        return {
            "status": "ok",
            "viewer": public_viewer(viewer),
            "history": state.get("history", []),
            "continue_reading": state.get("continue_reading"),
            "history_stats": state.get("history_stats", {}),
        }

    @router.put("/progress")
    async def api_save_user_progress(request: Request, payload: SaveProgressPayload):
        viewer = require_authenticated_viewer(request)

        try:
            progress = save_user_progress(int(viewer["user_id"]), payload.to_service_dict())
        except ChapterNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except UserStateError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {"status": "ok", "progress": progress}

    @router.post("/progress/reset")
    async def api_reset_user_progress(request: Request, payload: ResetProgressPayload):
        viewer = require_authenticated_viewer(request)

        try:
            result = reset_user_progress(int(viewer["user_id"]), payload.to_service_dict())
        except UserStateError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {"status": "ok", **result}

    @router.put("/library")
    async def api_save_user_library(request: Request, payload: SaveLibraryPayload):
        viewer = require_authenticated_viewer(request)

        try:
            library = save_user_library(int(viewer["user_id"]), payload.to_service_dict())
        except UserStateError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {"status": "ok", "library": library}

    return router
