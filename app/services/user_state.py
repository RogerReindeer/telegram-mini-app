"""User reading state service for the real v30/v31 Supabase schema.

The public API intentionally works with the current client compatibility shape,
while the database layer stores data in:
- user_novel_state
- user_chapter_progress
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..database import db_select, db_upsert, supabase_request


class UserStateError(ValueError):
    """Base error for invalid user-state operations."""


class ChapterNotFoundError(UserStateError):
    """Raised when a requested chapter does not belong to the requested novel."""


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "undefined"}:
        return ""
    return text


def to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    text = clean_value(value).replace("%", "").replace(",", ".")
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = clean_value(value).replace("%", "").replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def postgrest_in_filter(values: list[Any]) -> str:
    """Build a conservative PostgREST `in.(...)` filter for project IDs."""
    encoded: list[str] = []
    for value in values:
        text = clean_value(value)
        if not text:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+", text):
            raise UserStateError(f"Недопустимый идентификатор: {text}")
        encoded.append(text)
    return "in.(" + ",".join(encoded) + ")"


def rows_by_key(rows: list[dict], key: str) -> dict[str, dict]:
    return {
        clean_value(row.get(key)): row
        for row in rows
        if clean_value(row.get(key))
    }


def normalize_history_payload(progress_payload: list[dict[str, Any]], library_payload: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a reader-facing history shape from the storage-facing payload.

    The old ``progress`` key is kept for backwards compatibility. New clients can
    use ``history`` and ``continue_reading`` without knowing the raw DB column
    names.
    """
    finished_novel_ids = {
        to_int(row.get("novel_id"), 0)
        for row in library_payload
        if bool(row.get("is_completed") or row.get("is_finished"))
    }

    history: list[dict[str, Any]] = []
    for row in progress_payload:
        novel_id = to_int(row.get("novel_id"), 0)
        chapter_id = clean_value(row.get("chapter_id"))
        if novel_id <= 0 or not chapter_id:
            continue

        available = max(0, to_int(row.get("available_chapters"), 0))
        chapter_index = max(0, to_int(row.get("chapter_index"), 0))
        chapter_number = chapter_index + 1
        position = max(0.0, min(1.0, to_float(row.get("scroll_position"), 0.0)))
        chapter_progress_percent = int(round(position * 100))
        book_progress_percent = 0
        if available > 0:
            book_progress_percent = int(round(min(chapter_number, available) / available * 100))

        history.append({
            "novel_id": novel_id,
            "novel_slug": clean_value(row.get("novel_slug")),
            "novel_title": clean_value(row.get("novel_title")),
            "cover_url": clean_value(row.get("cover_url")),
            "chapter_id": chapter_id,
            "chapter_title": clean_value(row.get("chapter_title")),
            "chapter_index": chapter_index,
            "chapter_number": chapter_number,
            "available_chapters": available,
            "continue_url": f"/chapter/{chapter_id}",
            "scroll_position": position,
            "scroll_position_px": max(0, to_int(row.get("scroll_position_px"), 0)),
            "chapter_progress_percent": chapter_progress_percent,
            "book_progress_percent": book_progress_percent,
            "progress_label": f"Глава {chapter_number}" + (f" из {available}" if available else ""),
            "read_chapter_ids": row.get("read_chapter_ids") if isinstance(row.get("read_chapter_ids"), list) else [],
            "is_completed": novel_id in finished_novel_ids,
            "updated_at": clean_value(row.get("updated_at")),
        })

    history.sort(key=lambda item: clean_value(item.get("updated_at")), reverse=True)
    active_history = [item for item in history if not item.get("is_completed")]
    continue_reading = active_history[0] if active_history else (history[0] if history else None)

    return {
        "history": history,
        "continue_reading": continue_reading,
        "history_stats": {
            "items": len(history),
            "active_items": len(active_history),
            "completed_items": len(history) - len(active_history),
        },
    }


def get_user_state_rows(telegram_user_id: int) -> dict[str, Any]:
    state_rows = db_select(
        "user_novel_state",
        filters={"telegram_user_id": f"eq.{telegram_user_id}"},
        order="updated_at.desc",
    )
    chapter_progress_rows = db_select(
        "user_chapter_progress",
        filters={"telegram_user_id": f"eq.{telegram_user_id}"},
        order="last_read_at.desc",
    )

    novel_ids = sorted({
        to_int(row.get("novel_id"), 0)
        for row in state_rows
        if to_int(row.get("novel_id"), 0) > 0
    })

    progress_chapter_ids = [
        clean_value(row.get("chapter_id"))
        for row in chapter_progress_rows
        if clean_value(row.get("chapter_id"))
    ]

    progress_chapters: list[dict] = []
    for offset in range(0, len(progress_chapter_ids), 100):
        batch = progress_chapter_ids[offset:offset + 100]
        if not batch:
            continue
        progress_chapters.extend(db_select(
            "chapters",
            filters={"chapter_id": postgrest_in_filter(batch)},
        ))

    for chapter in progress_chapters:
        novel_id = to_int(chapter.get("novel_id"), 0)
        if novel_id > 0 and novel_id not in novel_ids:
            novel_ids.append(novel_id)
    novel_ids.sort()

    novels: list[dict] = []
    chapters: list[dict] = []
    for offset in range(0, len(novel_ids), 100):
        batch = novel_ids[offset:offset + 100]
        if not batch:
            continue
        numeric_filter = "in.(" + ",".join(str(value) for value in batch) + ")"
        novels.extend(db_select("novels", filters={"novel_id": numeric_filter}))
        chapters.extend(db_select(
            "chapters",
            filters={"novel_id": numeric_filter},
            order="novel_id.asc,chapter_no.asc",
        ))

    novel_by_id = {to_int(row.get("novel_id"), 0): row for row in novels}
    chapter_by_id = rows_by_key(chapters, "chapter_id")
    chapters_by_novel: dict[int, list[dict]] = {}
    for chapter in chapters:
        novel_id = to_int(chapter.get("novel_id"), 0)
        if novel_id > 0:
            chapters_by_novel.setdefault(novel_id, []).append(chapter)

    progress_by_novel: dict[int, list[dict]] = {}
    for progress in chapter_progress_rows:
        chapter = chapter_by_id.get(clean_value(progress.get("chapter_id")))
        if not chapter:
            continue
        novel_id = to_int(chapter.get("novel_id"), 0)
        if novel_id > 0:
            progress_by_novel.setdefault(novel_id, []).append(progress)

    state_by_novel = {
        to_int(row.get("novel_id"), 0): row
        for row in state_rows
        if to_int(row.get("novel_id"), 0) > 0
    }
    all_novel_ids = sorted(set(state_by_novel) | set(progress_by_novel))

    progress_payload: list[dict[str, Any]] = []
    library_payload: list[dict[str, Any]] = []

    for novel_id in all_novel_ids:
        state = state_by_novel.get(novel_id, {})
        novel = novel_by_id.get(novel_id, {})
        novel_progress = progress_by_novel.get(novel_id, [])
        latest_progress = novel_progress[0] if novel_progress else {}
        last_chapter_id = (
            clean_value(state.get("last_chapter_id"))
            or clean_value(latest_progress.get("chapter_id"))
        )
        chapter = chapter_by_id.get(last_chapter_id, {})
        ordered_chapters = chapters_by_novel.get(novel_id, [])
        chapter_index = 0
        for index, item in enumerate(ordered_chapters):
            if clean_value(item.get("chapter_id")) == last_chapter_id:
                chapter_index = index
                break

        read_ids = [
            clean_value(row.get("chapter_id"))
            for row in novel_progress
            if clean_value(row.get("chapter_id"))
        ]
        if last_chapter_id:
            progress_payload.append({
                "telegram_user_id": telegram_user_id,
                "novel_id": novel_id,
                "novel_slug": clean_value(novel.get("code")),
                "novel_title": clean_value(novel.get("novel_short")) or clean_value(novel.get("title_ru")),
                "cover_url": clean_value(novel.get("cover_url")),
                "chapter_id": last_chapter_id,
                "chapter_title": clean_value(chapter.get("chapter_title")),
                "chapter_index": chapter_index,
                "available_chapters": len(ordered_chapters),
                "scroll_position": to_float(latest_progress.get("progress_percent"), 0.0),
                "scroll_position_px": max(0, to_int(latest_progress.get("scroll_position"), 0)),
                "read_chapter_ids": read_ids,
                "updated_at": clean_value(state.get("last_read_at"))
                    or clean_value(latest_progress.get("last_read_at"))
                    or clean_value(state.get("updated_at")),
            })

        library_payload.append({
            **state,
            "novel_id": novel_id,
            "is_completed": bool(state.get("is_finished")),
            "is_hidden": bool(state.get("is_hidden")),
        })

    history_payload = normalize_history_payload(progress_payload, library_payload)

    return {
        "progress": progress_payload,
        "library": library_payload,
        "chapter_progress": chapter_progress_rows,
        **history_payload,
    }


def save_user_progress(telegram_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    novel_id = to_int(payload.get("novel_id"), 0)
    chapter_id = clean_value(payload.get("chapter_id"))
    if novel_id <= 0 or not chapter_id:
        raise UserStateError("Нужны novel_id и chapter_id")

    chapter_rows = db_select(
        "chapters",
        filters={
            "chapter_id": f"eq.{chapter_id}",
            "novel_id": f"eq.{novel_id}",
        },
        limit=1,
    )
    if not chapter_rows:
        raise ChapterNotFoundError("Глава не найдена или относится к другой новелле")

    progress_percent = max(0.0, min(1.0, to_float(payload.get("scroll_position"), 0.0)))
    scroll_position_px = max(0, to_int(payload.get("scroll_position_px"), 0))
    now_iso = utc_now().isoformat()

    progress_row = {
        "telegram_user_id": telegram_user_id,
        "chapter_id": chapter_id,
        "progress_percent": progress_percent,
        "scroll_position": scroll_position_px,
        "completed": bool(payload.get("completed", True)),
        "last_read_at": now_iso,
    }
    novel_state_row = {
        "telegram_user_id": telegram_user_id,
        "novel_id": novel_id,
        "is_reading": True,
        "is_finished": False,
        "last_chapter_id": chapter_id,
        "last_read_at": now_iso,
    }

    db_upsert(
        "user_chapter_progress",
        [progress_row],
        "telegram_user_id,chapter_id",
        batch_size=1,
    )
    db_upsert(
        "user_novel_state",
        [novel_state_row],
        "telegram_user_id,novel_id",
        batch_size=1,
    )

    return {
        **progress_row,
        "novel_id": novel_id,
        "scroll_position": progress_percent,
        "scroll_position_px": scroll_position_px,
    }


def reset_user_progress(telegram_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    novel_id = to_int(payload.get("novel_id"), 0)
    if novel_id <= 0:
        raise UserStateError("Нужен novel_id")

    chapter_rows = db_select(
        "chapters",
        select="chapter_id",
        filters={"novel_id": f"eq.{novel_id}"},
    )
    chapter_ids = [clean_value(row.get("chapter_id")) for row in chapter_rows if clean_value(row.get("chapter_id"))]
    for offset in range(0, len(chapter_ids), 100):
        batch = chapter_ids[offset:offset + 100]
        if not batch:
            continue
        supabase_request(
            "DELETE",
            "user_chapter_progress",
            params={
                "telegram_user_id": f"eq.{telegram_user_id}",
                "chapter_id": postgrest_in_filter(batch),
            },
            prefer="return=minimal",
        )

    supabase_request(
        "PATCH",
        "user_novel_state",
        params={
            "telegram_user_id": f"eq.{telegram_user_id}",
            "novel_id": f"eq.{novel_id}",
        },
        payload={
            "is_reading": False,
            "is_finished": False,
            "last_chapter_id": None,
            "last_read_at": None,
        },
        prefer="return=minimal",
    )
    return {"deleted_chapter_progress": len(chapter_ids)}


def save_user_library(telegram_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    novel_id = to_int(payload.get("novel_id"), 0)
    if novel_id <= 0:
        raise UserStateError("Нужен novel_id")

    existing_rows = db_select(
        "user_novel_state",
        filters={
            "telegram_user_id": f"eq.{telegram_user_id}",
            "novel_id": f"eq.{novel_id}",
        },
        limit=1,
    )
    existing = existing_rows[0] if existing_rows else {}
    is_finished = bool(payload.get("is_completed", payload.get("is_finished", False)))
    row = {
        "telegram_user_id": telegram_user_id,
        "novel_id": novel_id,
        "is_favorite": bool(payload.get("is_favorite")),
        "is_finished": is_finished,
        "is_hidden": bool(payload.get("is_hidden")),
        "is_reading": False if is_finished else bool(existing.get("is_reading")),
        "last_chapter_id": existing.get("last_chapter_id"),
        "last_read_at": existing.get("last_read_at"),
    }
    db_upsert("user_novel_state", [row], "telegram_user_id,novel_id", batch_size=1)
    return {**row, "is_completed": row["is_finished"]}
