from __future__ import annotations

from typing import Any
from .catalog import list_novels, list_chapters
from .access import decide_chapter_access
from .fixtures import CHAPTER_BODY


def public_viewer() -> dict[str, Any]:
    return {"telegram_user_id": None, "role": "guest", "role_label": "Гость"}


def prepare_library(viewer: dict[str, Any] | None = None) -> dict[str, Any]:
    novels = list_novels()
    continue_item = None
    if novels:
        chapters = list_chapters(novels[0]["id"])
        if chapters:
            second = chapters[1] if len(chapters) > 1 else chapters[0]
            continue_item = {"novel_title": novels[0].get("library_short_title") or novels[0].get("display_title"), "chapter_title": second.get("display_title"), "chapter_id": second.get("chapter_id")}
    return {"novels": novels, "continue_item": continue_item}


def prepare_novel(novel: dict[str, Any], viewer: dict[str, Any] | None = None) -> dict[str, Any]:
    chapters = []
    for chapter in list_chapters(novel["id"]):
        decision = decide_chapter_access(chapter, viewer)
        item = dict(chapter)
        item["is_available"] = decision.is_available
        item["access_label"] = decision.label
        chapters.append(item)
    return {"chapters": chapters, "hidden_subscriber_count": len([c for c in chapters if c.get("is_paid_extra")])}


def prepare_chapter(novel: dict[str, Any], chapter: dict[str, Any], chapters: list[dict[str, Any]], index: int, viewer: dict[str, Any] | None = None) -> dict[str, Any]:
    decision = decide_chapter_access(chapter, viewer)
    return {
        "chapter_index": index,
        "available_chapters": len([item for item in chapters if decide_chapter_access(item, viewer).is_available]),
        "is_locked": not decision.is_available,
        "telegraph_content": {"content_html": CHAPTER_BODY} if decision.is_available else None,
        "telegraph_error": None,
        "preview_text": "Эта глава пока закрыта. Доступ проверяется через подписку Boosty.",
        "access_copy": {"title": "Глава ждёт доступа", "description": "Если подписка уже оформлена, нажмите проверку доступа. Если доступа ещё нет, его можно получить на Boosty."},
        "previous_chapter": chapters[index - 1] if index > 0 else None,
        "next_chapter": chapters[index + 1] if index + 1 < len(chapters) else None,
    }
