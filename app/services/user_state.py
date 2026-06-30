from __future__ import annotations

from typing import Any
from .. import database
from ..contracts import USER_CHAPTER_PROGRESS_TABLE


def save_progress(payload: dict[str, Any]) -> dict[str, Any]:
    row = dict(payload)
    if database.is_configured():
        return database.upsert(USER_CHAPTER_PROGRESS_TABLE, [row], on_conflict="telegram_user_id,chapter_id")
    return {"ok": True, "stored": "local_client_queue_expected", "payload": row}


def get_history(telegram_user_id: str | int | None) -> dict[str, Any]:
    return {"history": [], "continue_reading": None}
