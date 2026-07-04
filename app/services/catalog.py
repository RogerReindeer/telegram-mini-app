from __future__ import annotations

from typing import Any

from ..database import db_select, supabase_ready
from ..cache import cache_get_or_set, catalog_cache_ttl
from ..utils import chapter_id_matches_parts, normalize_part_no_for_storage, parse_chapter_id
from .catalog_shared import (
    CHAPTER_TABLE_COLUMNS,
    FOX_TABLE_COLUMNS,
    KEY_MAP_CHAPTER,
    KEY_MAP_FOX,
    KEY_MAP_NOVEL,
    NOVEL_TABLE_COLUMNS,
    chapter_release_integrity_issues,
    normalize_dict_keys,
    normalize_fox_name,
    normalize_text_list,
)
from .reader import (
    clean_value,
    to_int,
    to_float,
    to_bool,
    parse_date,
    normalize_slug,
    is_date_open,
    chapter_display_title,
    parse_chapter_no_number,
)
from .telegraph import resolve_external_image_url

__all__ = [
    "adapt_chapter_from_db",
    "adapt_novel_from_db",
    "chapter_release_integrity_issues",
    "get_all_chapters",
    "get_all_novels",
    "get_chapter_by_id",
    "get_fox",
    "get_novel_by_id",
    "get_novel_by_slug",
    "get_novel_chapters",
    "normalize_chapter_row",
    "normalize_fox_row",
    "normalize_novel_row",
]


def filter_columns(row: dict, allowed_columns: set[str]) -> dict:
    return {key: value for key, value in row.items() if key in allowed_columns}


def normalize_novel_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_NOVEL)
    novel_id = to_int(row.get("novel_id"), 0)
    code = clean_value(row.get("code")) or str(novel_id)
    title_ru = clean_value(row.get("title_ru"))
    novel_short = clean_value(row.get("novel_short"))

    normalized = {
        "novel_id": novel_id,
        "code": code,
        "novel_short": novel_short or None,
        "title_ru": title_ru or novel_short or code,
        "title_en": clean_value(row.get("title_en")) or None,
        "title_original": clean_value(row.get("title_original")) or None,
        "original_language": clean_value(row.get("original_language")) or None,
        "post_icons": clean_value(row.get("post_icons")) or None,
        "status": clean_value(row.get("status")) or None,
        "access_model": clean_value(row.get("access_model")) or None,
        "schedule_mode": clean_value(row.get("schedule_mode")) or None,
        "early_access_mode": clean_value(row.get("early_access_mode")) or None,
        "release_year": to_int(row.get("release_year"), 0) or None,
        "author_original": clean_value(row.get("author_original")) or None,
        "author_latin": clean_value(row.get("author_latin")) or None,
        "author_cyrillic": clean_value(row.get("author_cyrillic")) or None,
        "author_translated": clean_value(row.get("author_translated")) or None,
        "cover_url": clean_value(row.get("cover_url")) or None,
        "description": clean_value(row.get("description")) or None,
        "top_description": clean_value(row.get("top_description")) or None,
        "bottom_description": clean_value(row.get("bottom_description")) or None,
        "miniapp_tags": normalize_text_list(row.get("miniapp_tags")),
        "tags_tg_catalog": clean_value(row.get("tags_tg_catalog")) or None,
        "tags_app_catalog": normalize_text_list(row.get("tags_app_catalog")),
        "miniapp_visible": to_bool(row.get("miniapp_visible"), True),
        "total_chapters": max(0, to_int(row.get("total_chapters"), 0)),
        "translated_chapters": max(0, to_int(row.get("translated_chapters"), 0)),
        "free_chapters": max(0, to_int(row.get("free_chapters"), 0)),
        "subscriber_chapters": max(0, to_int(row.get("subscriber_chapters"), 0)),
        "keeper_chapters": max(0, to_int(row.get("keeper_chapters"), 0)),
        "early_access_chapters": max(0, to_int(row.get("early_access_chapters"), 0)),
        "progress_percent": max(0.0, min(1.0, to_float(row.get("progress_percent"), 0.0))),
        "source_url_novelupdates": clean_value(row.get("source_url_novelupdates")) or None,
        "source_url_official": clean_value(row.get("source_url_official")) or None,
        "source_chapter_url": clean_value(row.get("source_chapter_url")) or None,
        "telegram_post_url": clean_value(row.get("telegram_post_url")) or None,
        "boosty_url": clean_value(row.get("boosty_url")) or None,
        "boosty_premium_url": clean_value(row.get("boosty_premium_url")) or None,
        "telegraph_catalog_url": clean_value(row.get("telegraph_catalog_url")) or None,
    }
    return filter_columns(normalized, NOVEL_TABLE_COLUMNS)


def normalize_chapter_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_CHAPTER)
    chapter_id = clean_value(row.get("chapter_id"))
    novel_id = to_int(row.get("novel_id"), 0)
    chapter_no = to_int(row.get("chapter_no"), 0)
    source_chapter_no = clean_value(row.get("source_chapter_no"))
    if not source_chapter_no and clean_value(row.get("chapter_no")):
        source_chapter_no = str(chapter_no)
    parsed_id = parse_chapter_id(chapter_id)
    part_no = normalize_part_no_for_storage(chapter_id, row.get("part_no"))
    if novel_id <= 0 or chapter_no < 0:
        raise ValueError("novel_id должен быть положительным, а chapter_no должен быть неотрицательным целым числом")
    if not parsed_id or not chapter_id_matches_parts(chapter_id, novel_id, chapter_no, part_no, source_chapter_no):
        raise ValueError(
            f"chapter_id {chapter_id!r} не соответствует NovelID/ChapterNo/SourceChapterNo/PartNo. "
            "ChapterID — это стабильный уникальный ключ строки; он может быть NovelID-ChapterNo "
            "или NovelID-SourceChapterNo-PartNo. Например: 13-0, 31-2, 2-52-1, 2-52-2."
        )
    normalized = {
        "chapter_id": chapter_id,
        "novel_id": novel_id,
        "volume_no": to_int(row.get("volume_no"), 0) if clean_value(row.get("volume_no")) else None,
        "volume_title": clean_value(row.get("volume_title")) or None,
        "chapter_no": chapter_no,
        "source_chapter_no": source_chapter_no or str(chapter_no),
        "part_no": part_no,
        "chapter_title": clean_value(row.get("chapter_title")) or None,
        "planned_translation_date": parse_date(row.get("planned_translation_date")),
        "translation_date": parse_date(row.get("translation_date")),
        "free_release_date": parse_date(row.get("free_release_date")),
        "premium_release_date": parse_date(row.get("premium_release_date")),
        "prepared_platforms": clean_value(row.get("prepared_platforms")) or None,
        "scheduled_platforms": clean_value(row.get("scheduled_platforms")) or None,
        "publishing_platforms": clean_value(row.get("publishing_platforms")) or None,
        "telegraph_premium_url": clean_value(row.get("telegraph_premium_url")) or None,
        "telegraph_premium_code": clean_value(row.get("telegraph_premium_code")) or None,
        "telegraph_free_url": clean_value(row.get("telegraph_free_url")) or None,
        "telegraph_free_code": clean_value(row.get("telegraph_free_code")) or None,
        "qa_status": to_bool(row.get("qa_status"), False),
    }
    return filter_columns(normalized, CHAPTER_TABLE_COLUMNS)


def adapt_novel_from_db(row: dict) -> dict:
    adapted = dict(row)
    novel_id = clean_value(row.get("novel_id"))
    short_title = clean_value(row.get("novel_short")) or clean_value(row.get("title_ru"))
    title_ru = clean_value(row.get("title_ru")) or short_title
    tags = row.get("miniapp_tags") or row.get("tags_app_catalog") or []
    if isinstance(tags, list):
        tags_text = "\n".join(clean_value(item) for item in tags if clean_value(item))
    else:
        tags_text = clean_value(tags)
    adapted.update({
        "id": novel_id,
        "slug": clean_value(row.get("code")) or normalize_slug(short_title or novel_id),
        "title": short_title,
        "short_title": short_title,
        "title_ru": title_ru,
        "full_title": title_ru,
        "title_en_original": clean_value(row.get("title_en")),
        "title_en": clean_value(row.get("title_en")),
        "tags": tags_text,
        "is_visible": to_bool(row.get("miniapp_visible"), True),
        "translation_status": clean_value(row.get("status")),
        "sort_order": to_float(row.get("novel_id"), 999999),
        "free_chapters_count": to_int(row.get("free_chapters"), 0),
        "traveler_chapters_count": to_int(row.get("subscriber_chapters"), 0),
        "keeper_chapters_count": to_int(row.get("keeper_chapters"), 0),
        "available_chapters_count": 0,
        "display_chapters_count": to_int(row.get("total_chapters"), 0),
        "added_date": None,
        "translation_author": clean_value(row.get("author_translated")),
    })
    return adapted


def adapt_chapter_from_db(row: dict) -> dict:
    adapted = dict(row)
    chapter_id = clean_value(row.get("chapter_id"))
    free_url = clean_value(row.get("telegraph_free_url"))
    premium_url = clean_value(row.get("telegraph_premium_url"))
    free_release_date = clean_value(row.get("free_release_date"))
    premium_release_date = clean_value(row.get("premium_release_date"))
    free_ready = bool(
        free_url
        and free_release_date
        and is_date_open(free_release_date)
    )
    premium_ready = bool(
        premium_url
        and premium_release_date
        and is_date_open(premium_release_date)
    )
    # There is no Traveler chapter tier. Premium-scheduled chapters belong to Keeper.
    access_level = "guest" if free_ready else "keeper"
    adapted.update({
        "chapter_code": chapter_id,
        "chapter_id": chapter_id,
        "source_chapter_no": clean_value(row.get("source_chapter_no")) or clean_value(row.get("chapter_no")),
        "part_no": clean_value(row.get("part_no")),
        "title": chapter_display_title(row),
        "sort_order": parse_chapter_no_number(row.get("chapter_no")),
        "is_visible": bool(free_url or premium_url),
        "access_level": access_level,
        "telegraph_url": premium_url or free_url,
    })
    return adapted


def normalize_fox_key(name: Any) -> str:
    return normalize_fox_name(name)


def normalize_fox_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_FOX)
    return filter_columns(
        {
            "name": normalize_fox_name(row.get("name")),
            "url": resolve_external_image_url(row.get("url")),
        },
        FOX_TABLE_COLUMNS,
    )


def _default_fox() -> dict[str, str]:
    return {
        "fox_side": "",
        "fox_pic": "",
        "fox_peek": "",
        "fox_peek_left": "",
        "fox_peek_right": "",
        "fox_sitting_front": "",
        "fox_sitting_side": "",
        "fox_sleeping": "",
        "fox_standing_paws_up": "",
        "fox_heart": "",
        "fox_jump_paws_up": "",
        "fox_laying_paws": "",
    }


def _load_fox_uncached() -> dict[str, str]:
    # Лисички берутся не из /static, а из таблицы fox,
    # которая синхронизируется из Excel/Google Sheets листа fox.
    # url может быть прямой ссылкой на картинку Teletype/Telegraph.
    default_fox = _default_fox()

    if not supabase_ready():
        return default_fox

    try:
        rows = db_select("fox", select="name,url")
    except Exception:
        return default_fox

    for row in rows:
        name = normalize_fox_name(row.get("name"))
        url = resolve_external_image_url(row.get("url"))

        if name and url:
            default_fox[name] = url

    return default_fox


def get_fox() -> dict[str, str]:
    return cache_get_or_set(
        "catalog:fox",
        catalog_cache_ttl(),
        _load_fox_uncached,
        namespace="catalog",
    )


def _load_all_novels_uncached(include_hidden: bool = False) -> list[dict]:
    if not supabase_ready():
        return []
    filters = None if include_hidden else {"miniapp_visible": "eq.true"}
    try:
        rows = db_select("novels", select="*", filters=filters, order="novel_id.asc")
        return [adapt_novel_from_db(row) for row in rows]
    except Exception as error:
        print("get_all_novels error:", error)
        return []


def get_all_novels(include_hidden: bool = False) -> list[dict]:
    return cache_get_or_set(
        f"catalog:novels:include_hidden={int(include_hidden)}",
        catalog_cache_ttl(),
        lambda: _load_all_novels_uncached(include_hidden),
        namespace="catalog",
    )


def _load_all_chapters_uncached() -> list[dict]:
    if not supabase_ready():
        return []
    try:
        rows = db_select("chapters", select="*", order="novel_id.asc,chapter_no.asc")
        return [adapt_chapter_from_db(row) for row in rows]
    except Exception as error:
        print("get_all_chapters error:", error)
        return []


def get_all_chapters() -> list[dict]:
    return cache_get_or_set(
        "catalog:chapters:all",
        catalog_cache_ttl(),
        _load_all_chapters_uncached,
        namespace="catalog",
    )


def _load_novel_by_slug_uncached(slug: str, include_hidden: bool = False) -> dict | None:
    if not supabase_ready():
        return None
    filters = {"code": f"eq.{slug}"}
    if not include_hidden:
        filters["miniapp_visible"] = "eq.true"
    rows = db_select("novels", select="*", filters=filters, limit=1)
    return adapt_novel_from_db(rows[0]) if rows else None


def get_novel_by_slug(slug: str, include_hidden: bool = False) -> dict | None:
    return cache_get_or_set(
        f"catalog:novel_by_slug:{slug}:include_hidden={int(include_hidden)}",
        catalog_cache_ttl(),
        lambda: _load_novel_by_slug_uncached(slug, include_hidden),
        namespace="catalog",
    )


def _load_novel_chapters_uncached(novel_id: str) -> list[dict]:
    if not supabase_ready():
        return []
    rows = db_select("chapters", select="*", filters={"novel_id": f"eq.{novel_id}"}, order="chapter_no.asc")
    return [adapt_chapter_from_db(row) for row in rows]


def get_novel_chapters(novel_id: str) -> list[dict]:
    return cache_get_or_set(
        f"catalog:novel_chapters:{novel_id}",
        catalog_cache_ttl(),
        lambda: _load_novel_chapters_uncached(novel_id),
        namespace="catalog",
    )


def _load_chapter_by_id_uncached(chapter_id: str) -> dict | None:
    if not supabase_ready():
        return None
    rows = db_select("chapters", select="*", filters={"chapter_id": f"eq.{chapter_id}"}, limit=1)
    return adapt_chapter_from_db(rows[0]) if rows else None


def get_chapter_by_id(chapter_id: str) -> dict | None:
    return cache_get_or_set(
        f"catalog:chapter_by_id:{chapter_id}",
        catalog_cache_ttl(),
        lambda: _load_chapter_by_id_uncached(chapter_id),
        namespace="catalog",
    )


def _load_novel_by_id_uncached(novel_id: str) -> dict | None:
    if not supabase_ready():
        return None
    rows = db_select("novels", select="*", filters={"novel_id": f"eq.{novel_id}"}, limit=1)
    return adapt_novel_from_db(rows[0]) if rows else None


def get_novel_by_id(novel_id: str) -> dict | None:
    return cache_get_or_set(
        f"catalog:novel_by_id:{novel_id}",
        catalog_cache_ttl(),
        lambda: _load_novel_by_id_uncached(novel_id),
        namespace="catalog",
    )

