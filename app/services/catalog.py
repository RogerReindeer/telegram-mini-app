from __future__ import annotations

from typing import Any
from .. import database
from ..contracts import NOVELS_TABLE, CHAPTERS_TABLE, FOX_TABLE
from ..utils import normalize_slug, to_int
from .fixtures import NOVELS, CHAPTERS, FOX


def list_novels() -> list[dict[str, Any]]:
    rows = database.select(NOVELS_TABLE, {"select": "*", "order": "sort_order.asc"}) if database.is_configured() else []
    if not rows:
        return NOVELS
    return [adapt_novel(row) for row in rows]


def get_novel_by_slug(slug: str) -> dict[str, Any] | None:
    return next((novel for novel in list_novels() if novel.get("slug") == slug), None)


def list_chapters(novel_id: int | str) -> list[dict[str, Any]]:
    nid = to_int(novel_id)
    rows = database.select(CHAPTERS_TABLE, {"select": "*", "novel_id": f"eq.{nid}", "order": "chapter_no.asc"}) if database.is_configured() else []
    if not rows:
        return CHAPTERS.get(nid, [])
    return [adapt_chapter(row) for row in rows]


def get_fox() -> dict[str, str]:
    rows = database.select(FOX_TABLE, {"select": "*", "limit": "1"}) if database.is_configured() else []
    if not rows:
        return FOX
    return {key: value for key, value in rows[0].items() if value}


def find_chapter(chapter_id: str) -> tuple[dict[str, Any], dict[str, Any], int] | None:
    for novel in list_novels():
        chapters = list_chapters(novel.get("id"))
        for index, chapter in enumerate(chapters):
            if str(chapter.get("chapter_id")) == str(chapter_id):
                return novel, chapter, index
    return None


def adapt_novel(row: dict[str, Any]) -> dict[str, Any]:
    title = row.get("display_title") or row.get("title") or row.get("NovelTitle") or "Без названия"
    tags = row.get("catalog_tag_items") or []
    if isinstance(tags, str):
        tags = [{"text": item.strip(), "class_name": "tag-soft", "is_spoiler": False} for item in tags.split(",") if item.strip()]
    return {
        "id": to_int(row.get("id") or row.get("novel_id") or row.get("NovelID")),
        "slug": row.get("slug") or normalize_slug(title),
        "display_title": title,
        "library_short_title": row.get("library_short_title") or row.get("short_title") or title,
        "library_secondary_title": row.get("library_secondary_title") or row.get("full_title") or title,
        "cover_url": row.get("cover_url") or "",
        "age_rating": row.get("age_rating") or "",
        "translation_status": row.get("translation_status") or "active",
        "translation_status_label": row.get("translation_status_label") or "🛠 В работе",
        "translation_status_color": row.get("translation_status_color") or "#6f9b72",
        "show_access_badge": bool(row.get("show_access_badge", True)),
        "access_badge": row.get("access_badge") or {"icon": "🌱", "label": "Boosty"},
        "free_chapters_count": to_int(row.get("free_chapters_count")),
        "keeper_chapters_count": to_int(row.get("keeper_chapters_count")),
        "translated_chapters": to_int(row.get("translated_chapters")),
        "total_chapters": to_int(row.get("total_chapters")),
        "description": row.get("description") or "",
        "description_paragraphs": row.get("description_paragraphs") or [],
        "top_description": row.get("top_description") or "",
        "bottom_description": row.get("bottom_description") or "",
        "catalog_tag_items": tags,
        "card_tag_items": tags,
    }


def adapt_chapter(row: dict[str, Any]) -> dict[str, Any]:
    chapter_id = row.get("chapter_id") or row.get("ChapterID")
    return {
        "chapter_id": chapter_id,
        "display_title": row.get("display_title") or row.get("chapter_title") or f"Глава {row.get('source_chapter_no') or row.get('chapter_no') or ''}",
        "access_label": row.get("access_label") or "🌱 Открыто",
        "access_class": row.get("access_class") or "chapter-access-free",
        "required_role": row.get("required_role") or "guest",
        "is_available": bool(row.get("is_available", True)),
        "is_paid_extra": bool(row.get("is_paid_extra", False)),
        "sort_value": to_int(row.get("sort_value") or row.get("chapter_no")),
        "source_chapter_no": row.get("source_chapter_no") or row.get("chapter_no"),
        "part_no": row.get("part_no"),
        "volume_title": row.get("volume_title") or "",
        "public_url": row.get("public_url") or row.get("telegraph_url") or "",
        "premium_url": row.get("premium_url") or "",
    }
