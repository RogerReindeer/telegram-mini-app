from __future__ import annotations

import re
from typing import Any

from ..database import db_select, supabase_ready
from ..cache import cache_get_or_set, catalog_cache_ttl
from ..utils import expected_chapter_id, parse_chapter_id
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
from .sync import parse_iso_datetime
from .telegraph import resolve_external_image_url

NOVEL_TABLE_COLUMNS = {
    "novel_id", "code", "novel_short", "title_ru", "title_en", "title_original",
    "original_language", "post_icons", "status", "access_model", "schedule_mode",
    "early_access_mode", "release_year", "author_original", "author_latin",
    "author_cyrillic", "author_translated", "cover_url", "description",
    "top_description", "bottom_description", "miniapp_tags", "tags_tg_catalog",
    "tags_app_catalog", "miniapp_visible", "total_chapters", "translated_chapters",
    "free_chapters", "subscriber_chapters", "keeper_chapters",
    "early_access_chapters", "progress_percent", "source_url_novelupdates",
    "source_url_official", "source_chapter_url", "telegram_post_url", "boosty_url",
    "boosty_premium_url", "telegraph_catalog_url",
}

CHAPTER_TABLE_COLUMNS = {
    "chapter_id", "novel_id", "volume_no", "volume_title", "chapter_no",
    "source_chapter_no", "part_no", "chapter_title", "planned_translation_date", "translation_date",
    "free_release_date", "premium_release_date", "prepared_platforms",
    "scheduled_platforms", "publishing_platforms", "telegraph_premium_url",
    "telegraph_premium_code", "telegraph_free_url", "telegraph_free_code",
    "qa_status",
}

FOX_TABLE_COLUMNS = {"name", "url"}

KEY_MAP_NOVEL = {
    "NovelID": "novel_id", "Code": "code", "NovelShort": "novel_short",
    "TitleRU": "title_ru", "TitleRu": "title_ru", "TitleEN": "title_en",
    "TitleOriginal": "title_original", "OriginalLanguage": "original_language",
    "PostIcons": "post_icons", "Status": "status", "AccessModel": "access_model",
    "ScheduleMode": "schedule_mode", "EarlyAccessMode": "early_access_mode",
    "ReleaseYear": "release_year", "AuthorOriginal": "author_original",
    "AuthorLatin": "author_latin", "AuthorCyrillic": "author_cyrillic",
    "AuthorTranslated": "author_translated", "CoverURL": "cover_url",
    "Description": "description", "TopDescription": "top_description",
    "BottomDescription": "bottom_description", "MiniAppTags": "miniapp_tags",
    "TagsTGCatalog": "tags_tg_catalog", "TagsAppCatalog": "tags_app_catalog",
    "MiniAppVisible": "miniapp_visible", "TotalChapters": "total_chapters",
    "TranslatedChapters": "translated_chapters", "FreeChapters": "free_chapters",
    "SubscriberChapters": "subscriber_chapters", "KeeperChapters": "keeper_chapters",
    "EarlyAccessChapters": "early_access_chapters", "ProgressPercent": "progress_percent",
    "SourceURLNovelupdates": "source_url_novelupdates", "SourceURLOfficial": "source_url_official",
    "SourceChapterURL": "source_chapter_url", "TelegramPostURL": "telegram_post_url",
    "BoostyURL": "boosty_url", "BoostyPremiumURL": "boosty_premium_url",
    "TelegraphCatalogURL": "telegraph_catalog_url",
}

KEY_MAP_CHAPTER = {
    "ChapterID": "chapter_id", "NovelID": "novel_id", "VolumeNo": "volume_no",
    "VolumeTitle": "volume_title", "ChapterNo": "chapter_no",
    "SourceChapterNo": "source_chapter_no", "PartNo": "part_no",
    "ChapterTitle": "chapter_title", "PlannedTranslationDate": "planned_translation_date",
    "TranslationDate": "translation_date", "FreeReleaseDate": "free_release_date",
    "PremiumReleaseDate": "premium_release_date", "PreparedPlatforms": "prepared_platforms",
    "ScheduledPlatforms": "scheduled_platforms", "PublishingPlatforms": "publishing_platforms",
    "TelegraphPremiumURL": "telegraph_premium_url",
    "TelegraphPremiumCode": "telegraph_premium_code", "TelegraphFreeURL": "telegraph_free_url",
    "TelegraphFreeCode": "telegraph_free_code", "QAStatus": "qa_status",
}

KEY_MAP_FOX = {
    "Name": "name",
    "name": "name",
    "Название": "name",
    "Fox": "name",
    "fox": "name",
    "URL": "url",
    "Url": "url",
    "url": "url",
    "Ссылка": "url",
    "ImageURL": "url",
    "ImageUrl": "url",
}

def normalize_dict_keys(row: dict, key_map: dict[str, str]) -> dict:
    return {key_map.get(key, key): value for key, value in row.items()}


def filter_columns(row: dict, allowed_columns: set[str]) -> dict:
    return {key: value for key, value in row.items() if key in allowed_columns}


def _normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = re.split(r"[\n,;]+", clean_value(value))
    result = []
    seen = set()
    for item in raw:
        text = clean_value(item)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


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
        "miniapp_tags": _normalize_text_list(row.get("miniapp_tags")),
        "tags_tg_catalog": clean_value(row.get("tags_tg_catalog")) or None,
        "tags_app_catalog": _normalize_text_list(row.get("tags_app_catalog")),
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
    parsed_id = parse_chapter_id(chapter_id)
    explicit_part_no = to_int(row.get("part_no"), 0) if clean_value(row.get("part_no")) else None
    part_no = explicit_part_no if explicit_part_no else (parsed_id or {}).get("part_no")
    if novel_id <= 0 or chapter_no <= 0:
        raise ValueError("novel_id и chapter_no должны быть положительными целыми числами")
    expected_id = expected_chapter_id(novel_id, chapter_no, part_no)
    if not parsed_id or chapter_id != expected_id:
        raise ValueError(
            f"chapter_id {chapter_id!r} должен быть равен {expected_id!r}. "
            "Поддерживаются формы NovelID-ChapterNo и NovelID-ChapterNo-PartNo, например 2-50, 2-52-1, 2-52-2."
        )
    normalized = {
        "chapter_id": chapter_id,
        "novel_id": novel_id,
        "volume_no": to_int(row.get("volume_no"), 0) if clean_value(row.get("volume_no")) else None,
        "volume_title": clean_value(row.get("volume_title")) or None,
        "chapter_no": chapter_no,
        "source_chapter_no": clean_value(row.get("source_chapter_no")) or str(chapter_no),
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


def chapter_release_integrity_issues(chapter: dict) -> list[str]:
    """Return sync-time warnings for dangerous or inconsistent release rows.

    These warnings do not reject the row: MiniApp stays fail-closed and stores the
    data, while the sync result tells the editor what must be fixed in Excel.
    """
    issues: list[str] = []
    chapter_id = clean_value(chapter.get("chapter_id")) or "?"
    translated = bool(clean_value(chapter.get("translation_date")))
    free_date = clean_value(chapter.get("free_release_date"))
    premium_date = clean_value(chapter.get("premium_release_date"))
    free_url = clean_value(chapter.get("telegraph_free_url")) or clean_value(chapter.get("telegraph_free_code"))
    premium_url = clean_value(chapter.get("telegraph_premium_url")) or clean_value(chapter.get("telegraph_premium_code"))

    if translated and (free_url or premium_url) and not free_date and not premium_date:
        issues.append(f"{chapter_id}: переведена и имеет ссылку, но нет ни FreeReleaseDate, ни PremiumReleaseDate; в MiniApp закрыта")

    if free_url and not free_date:
        issues.append(f"{chapter_id}: есть бесплатная ссылка, но нет FreeReleaseDate; бесплатный доступ закрыт")

    if premium_url and not premium_date:
        issues.append(f"{chapter_id}: есть премиальная ссылка, но нет PremiumReleaseDate; доступ Хранителя закрыт")

    if free_date and not free_url:
        issues.append(f"{chapter_id}: назначена FreeReleaseDate, но нет бесплатной ссылки/кода")

    if premium_date and not premium_url:
        issues.append(f"{chapter_id}: назначена PremiumReleaseDate, но нет премиальной ссылки/кода")

    if free_date and premium_date:
        try:
            premium_dt = parse_iso_datetime(premium_date)
            free_dt = parse_iso_datetime(free_date)
            if premium_dt and free_dt and premium_dt > free_dt:
                issues.append(f"{chapter_id}: PremiumReleaseDate позже FreeReleaseDate")
        except Exception:
            issues.append(f"{chapter_id}: не удалось сравнить даты релизов")

    return issues

def normalize_fox_name(value: Any) -> str:
    name = clean_value(value)

    if not name:
        return ""

    # В листе fox имя может быть записано как fox_side.png, fox_pic.jpg и т.п.
    # Для сайта это должен быть чистый ключ: fox_side, fox_pic.
    name = re.sub(r"\.(png|jpg|jpeg|webp|gif)$", "", name.strip(), flags=re.IGNORECASE)
    name = name.lower()
    name = name.replace("-", "_").replace(" ", "_")
    name = re.sub(r"[^a-z0-9_а-яё]+", "", name)
    name = re.sub(r"_+", "_", name).strip("_")

    aliases = {
        "peek": "fox_peek",
        "foxpeek": "fox_peek",
        "fox_peek": "fox_peek",
        "fox_peek_png": "fox_peek",
        "pic": "fox_pic",
        "foxpic": "fox_pic",
        "fox_pic": "fox_pic",
        "fox_pic_png": "fox_pic",
        "side": "fox_side",
        "foxside": "fox_side",
        "fox_side": "fox_side",
        "fox_side_png": "fox_side",
        "sitting": "fox_sitting_front",
        "sitting_front": "fox_sitting_front",
        "foxsittingfront": "fox_sitting_front",
        "fox_sitting_front": "fox_sitting_front",
        "fox_sitting_front_png": "fox_sitting_front",
        "fox_sitting_side": "fox_sitting_side",
        "fox_sitting_side_png": "fox_sitting_side",
        "fox_sleeping": "fox_sleeping",
        "fox_sleeping_png": "fox_sleeping",
        "fox_standing_paws_up": "fox_standing_paws_up",
        "fox_standing_paws_up_png": "fox_standing_paws_up",
        "fox_heart": "fox_heart",
        "fox_heart_png": "fox_heart",
        "fox_jump_paws_up": "fox_jump_paws_up",
        "fox_jump_paws_up_png": "fox_jump_paws_up",
        "fox_laying_paws": "fox_laying_paws",
        "fox_laying_paws_png": "fox_laying_paws",
        "fox_peek_left": "fox_peek_left",
        "fox_peek_left_png": "fox_peek_left",
        "fox_peek_right": "fox_peek_right",
        "fox_peek_right_png": "fox_peek_right",
        "лисичка_сбоку": "fox_side",
        "лисичка_в_шапке": "fox_peek",
        "лисичка": "fox_pic",
    }

    return aliases.get(name, name)


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

