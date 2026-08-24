from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request

from ..schemas import ResetProgressPayload, SaveLibraryPayload, SaveProgressPayload
from ..services.user_state import get_user_state_rows, reset_user_progress, save_user_library, save_user_progress
from ..services.analytics import personal_reading_stats


def create_user_router(require_app_access_viewer: Callable, public_viewer: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/user")

    def viewer(request: Request) -> dict:
        return require_app_access_viewer(request)

    def user_id_from_viewer(current: dict) -> int:
        return int(current.get("user_id") or current.get("telegram_user_id") or 0)

    def admin_preview_state() -> dict:
        # Browser QA under the signed admin session must never create a fake
        # Telegram identity or pollute real progress. The frontend receives the
        # same shape as an empty account and can render normally.
        return {
            "progress": [],
            "library": [],
            "chapter_progress": [],
            "history": [],
            "continue_reading": None,
            "history_stats": {"items": 0, "active_items": 0, "completed_items": 0},
            "admin_preview": True,
            "read_only": True,
        }

    def admin_preview_stats() -> dict:
        return {
            "chapters_opened": 0,
            "chapters_read": 0,
            "chapters_finished": 0,
            "novels_started": 0,
            "novels_completed": 0,
            "currently_reading": 0,
            "last_read_at": "",
            "admin_preview": True,
            "read_only": True,
        }

    def preview_noop() -> dict:
        return {"status": "ignored", "reason": "admin_preview_read_only", "admin_preview": True}

    @router.get("/state")
    def state(request: Request):
        current = viewer(request)
        if current.get("admin_preview"):
            return admin_preview_state()
        return get_user_state_rows(user_id_from_viewer(current))

    @router.get("/history")
    def history(request: Request):
        current = viewer(request)
        if current.get("admin_preview"):
            return []
        return get_user_state_rows(user_id_from_viewer(current)).get("history", [])

    @router.get("/stats")
    def stats(request: Request):
        current = viewer(request)
        if current.get("admin_preview"):
            return admin_preview_stats()
        return personal_reading_stats(user_id_from_viewer(current))

    @router.put("/progress")
    def progress(request: Request, payload: SaveProgressPayload):
        current = viewer(request)
        if current.get("admin_preview"):
            return preview_noop()
        return save_user_progress(user_id_from_viewer(current), payload.to_service_dict())

    @router.post("/progress/reset")
    def reset_progress(request: Request, payload: ResetProgressPayload):
        current = viewer(request)
        if current.get("admin_preview"):
            return preview_noop()
        return reset_user_progress(user_id_from_viewer(current), payload.to_service_dict())

    @router.put("/library")
    def library(request: Request, payload: SaveLibraryPayload):
        current = viewer(request)
        if current.get("admin_preview"):
            return preview_noop()
        return save_user_library(user_id_from_viewer(current), payload.to_service_dict())

    return router
