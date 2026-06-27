"""Service layer for Translation CRM -> MiniApp -> Supabase sync.

This module owns payload validation/normalization and all Supabase writes for
``POST /sync`` and ``POST /api/sync``. Routers should not talk to Supabase
or know spreadsheet column aliases directly.
"""

from __future__ import annotations

import re
import traceback
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from ..cache import clear_catalog_cache, clear_image_cache, clear_telegraph_cache
from ..database import db_insert, db_update, db_upsert, supabase_ready

EXPECTED_SCHEMA_VERSION = 17

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


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("nan", "none", "null", "undefined"):
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


def to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = clean_value(value).lower()
    if not text:
        return default
    if text in ("true", "1", "yes", "y", "да", "истина", "visible", "show", "✓", "✅"):
        return True
    if text in ("false", "0", "no", "n", "нет", "ложь", "hidden", "hide", "✕", "❌"):
        return False
    return default


def parse_date(value: Any) -> str | None:
    """Normalize a spreadsheet date for PostgreSQL/Supabase DATE columns."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    text = str(value).strip()
    if not text:
        return None

    text = text.replace('\\"', '"').replace("\\'", "'").strip()
    for _ in range(5):
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
            text = text[1:-1].strip()
        else:
            break

    if not text:
        return None

    if text.lower() in {'null', 'none', 'undefined', 'nan', 'nat', 'n/a', 'na', '-', '—', '""', "''"}:
        return None

    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[T\s].*)?$", text)
    if iso_match:
        candidate = iso_match.group(1)
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None

    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y.%m.%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    return None


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def parse_iso_datetime(value: Any) -> datetime | None:
    text = clean_value(value)
    if not text:
        return None
    parsed_date = parse_date(text)
    if parsed_date:
        return datetime.fromisoformat(parsed_date + "T00:00:00+00:00")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_date_open(value: Any) -> bool:
    date_text = parse_date(value)
    if not date_text:
        return False
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text):
        return True
    return date_text <= today_iso()


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
    result: list[str] = []
    seen: set[str] = set()
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
    if novel_id <= 0 or chapter_no <= 0:
        raise ValueError("novel_id и chapter_no должны быть положительными целыми числами")
    expected_chapter_id = f"{novel_id}-{chapter_no}"
    if chapter_id != expected_chapter_id:
        raise ValueError(f"chapter_id {chapter_id!r} должен быть равен {expected_chapter_id!r}")

    normalized = {
        "chapter_id": chapter_id,
        "novel_id": novel_id,
        "volume_no": to_int(row.get("volume_no"), 0) if clean_value(row.get("volume_no")) else None,
        "volume_title": clean_value(row.get("volume_title")) or None,
        "chapter_no": chapter_no,
        "source_chapter_no": clean_value(row.get("source_chapter_no")) or str(chapter_no),
        "part_no": to_int(row.get("part_no"), 0) if clean_value(row.get("part_no")) else None,
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


def normalize_fox_name(value: Any) -> str:
    name = clean_value(value)
    if not name:
        return ""
    name = re.sub(r"\.(png|jpg|jpeg|webp|gif)$", "", name.strip(), flags=re.IGNORECASE)
    name = name.lower().replace("-", "_").replace(" ", "_")
    name = re.sub(r"[^a-z0-9_а-яё]+", "", name)
    name = re.sub(r"_+", "_", name).strip("_")
    aliases = {
        "peek": "fox_peek",
        "foxpeek": "fox_peek",
        "fox_peek_png": "fox_peek",
        "pic": "fox_pic",
        "foxpic": "fox_pic",
        "fox_pic_png": "fox_pic",
        "side": "fox_side",
        "foxside": "fox_side",
        "fox_side_png": "fox_side",
        "sitting": "fox_sitting_front",
        "sitting_front": "fox_sitting_front",
        "foxsittingfront": "fox_sitting_front",
        "fox_sitting_front_png": "fox_sitting_front",
        "лисичка_сбоку": "fox_side",
        "лисичка_в_шапке": "fox_peek",
        "лисичка": "fox_pic",
    }
    return aliases.get(name, name)


def resolve_external_image_url(value: Any) -> str:
    url = clean_value(value)
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://"):
        return "https://" + url[7:]
    return url


def normalize_fox_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_FOX)
    return filter_columns(
        {"name": normalize_fox_name(row.get("name")), "url": resolve_external_image_url(row.get("url"))},
        FOX_TABLE_COLUMNS,
    )


def chapter_release_integrity_issues(chapter: dict) -> list[str]:
    """Return sync-time warnings for dangerous or inconsistent release rows."""
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


def _coerce_payload_collection(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def validate_sync_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a MiniApp sync payload without writing to Supabase."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "source": "Translation CRM",
            "schema_version": EXPECTED_SCHEMA_VERSION,
            "novels": [],
            "chapters": [],
            "fox": [],
            "errors": ["Корень JSON должен быть объектом."],
            "warnings": [],
        }

    source = clean_value(payload.get("source")) or "Translation CRM"
    schema_version = to_int(payload.get("schema_version"), 0) or EXPECTED_SCHEMA_VERSION

    if schema_version != EXPECTED_SCHEMA_VERSION:
        errors.append(
            f"Неподдерживаемая версия схемы: {schema_version}. "
            f"Ожидается {EXPECTED_SCHEMA_VERSION}."
        )

    novels_raw = _coerce_payload_collection(payload.get("novels") or payload.get("Novels") or [])
    chapters_raw = _coerce_payload_collection(payload.get("chapters") or payload.get("Chapters") or [])
    fox_raw = _coerce_payload_collection(payload.get("fox") or payload.get("Fox") or [])

    novels: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    fox_rows: list[dict[str, Any]] = []

    seen_novel_ids: set[int] = set()
    seen_chapter_ids: set[str] = set()
    seen_fox_names: set[str] = set()

    for index, raw in enumerate(novels_raw):
        label = f"novels[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label}: строка должна быть объектом.")
            continue
        try:
            row = normalize_novel_row(raw)
        except Exception as error:
            errors.append(f"{label}: {error}")
            continue

        novel_id = to_int(row.get("novel_id"), 0)
        if novel_id <= 0:
            errors.append(f"{label}: отсутствует или некорректен novel_id.")
            continue
        if novel_id in seen_novel_ids:
            errors.append(f"{label}: повторяется novel_id={novel_id}.")
            continue
        if not clean_value(row.get("title_ru")):
            errors.append(f"{label}: отсутствует title_ru.")
            continue
        if not clean_value(row.get("cover_url")):
            warnings.append(f"NovelID {novel_id}: отсутствует обложка.")
        if not clean_value(row.get("description")):
            warnings.append(f"NovelID {novel_id}: отсутствует описание.")
        seen_novel_ids.add(novel_id)
        novels.append(row)

    for index, raw in enumerate(chapters_raw):
        label = f"chapters[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label}: строка должна быть объектом.")
            continue
        try:
            row = normalize_chapter_row(raw)
        except Exception as error:
            errors.append(f"{label}: {error}")
            continue

        chapter_id = clean_value(row.get("chapter_id"))
        novel_id = to_int(row.get("novel_id"), 0)

        if not chapter_id:
            errors.append(f"{label}: отсутствует chapter_id.")
            continue
        if chapter_id in seen_chapter_ids:
            errors.append(f"{label}: повторяется chapter_id={chapter_id}.")
            continue
        if novel_id not in seen_novel_ids:
            errors.append(f"{label}: NovelID {novel_id} отсутствует среди отправляемых новелл.")
            continue

        seen_chapter_ids.add(chapter_id)
        chapters.append(row)

    for index, raw in enumerate(fox_raw):
        label = f"fox[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label}: строка должна быть объектом.")
            continue
        try:
            row = normalize_fox_row(raw)
        except Exception as error:
            errors.append(f"{label}: {error}")
            continue

        name = clean_value(row.get("name"))
        url = clean_value(row.get("url"))
        if not name or not url:
            errors.append(f"{label}: отсутствует name или url.")
            continue
        if name in seen_fox_names:
            errors.append(f"{label}: повторяется name={name}.")
            continue
        seen_fox_names.add(name)
        fox_rows.append(row)

    release_warnings = [issue for chapter in chapters for issue in chapter_release_integrity_issues(chapter)]
    warnings.extend(release_warnings)

    # Сохраняем порядок, но убираем полные дубли предупреждений.
    unique_warnings: list[str] = []
    seen_warnings: set[str] = set()
    for warning in warnings:
        key = warning.casefold()
        if key in seen_warnings:
            continue
        seen_warnings.add(key)
        unique_warnings.append(warning)

    return {
        "ok": len(errors) == 0,
        "source": source,
        "schema_version": schema_version,
        "novels": novels,
        "chapters": chapters,
        "fox": fox_rows,
        "errors": errors,
        "warnings": unique_warnings,
    }


def normalize_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    validation = validate_sync_payload(payload)
    if validation["errors"]:
        raise HTTPException(status_code=400, detail={"errors": validation["errors"][:100]})
    return validation["novels"], validation["chapters"], validation["fox"]


def build_validation_response(payload: dict[str, Any]) -> dict[str, Any]:
    validation = validate_sync_payload(payload)
    return {
        "status": "ok" if validation["ok"] else "error",
        "mode": "validate",
        "source": validation["source"],
        "schema_version": validation["schema_version"],
        "expected_schema_version": EXPECTED_SCHEMA_VERSION,
        "novels_received": len(validation["novels"]),
        "chapters_received": len(validation["chapters"]),
        "fox_received": len(validation["fox"]),
        "errors_count": len(validation["errors"]),
        "errors": validation["errors"][:100],
        "warnings_count": len(validation["warnings"]),
        "warnings": validation["warnings"][:100],
        "would_write": False,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_sync_run(source: str, schema_version: int) -> int | None:
    try:
        rows = db_insert(
            "sync_runs",
            {
                "source": source or "Translation CRM",
                "schema_version": schema_version or EXPECTED_SCHEMA_VERSION,
                "status": "running",
                "started_at": _utc_now_iso(),
            },
            prefer="return=representation",
        )
        if rows and isinstance(rows[0], dict):
            return to_int(rows[0].get("sync_id"), 0) or None
    except Exception as error:
        print("Could not create sync_runs row:", error)
    return None


def _finish_sync_run(sync_id: int | None, patch: dict[str, Any]) -> None:
    if not sync_id:
        return
    try:
        payload = dict(patch)
        payload["finished_at"] = _utc_now_iso()
        db_update("sync_runs", {"sync_id": f"eq.{sync_id}"}, payload)
    except Exception as error:
        print("Could not update sync_runs row:", error)


async def run_sync(payload: dict[str, Any]) -> JSONResponse:
    """Normalize sync payload, record sync_runs, and upsert it into Supabase."""
    if not supabase_ready():
        return JSONResponse(
            {
                "status": "error",
                "stage": "configuration",
                "detail": "На Render не настроены SUPABASE_URL и SUPABASE_KEY/SUPABASE_SERVICE_KEY.",
            },
            status_code=500,
        )

    stage = "validation"
    sync_id: int | None = None

    try:
        if not isinstance(payload, dict):
            payload = {}

        validation = validate_sync_payload(payload)
        sync_id = _create_sync_run(validation["source"], validation["schema_version"])

        if validation["errors"]:
            _finish_sync_run(
                sync_id,
                {
                    "status": "error",
                    "novels_count": len(validation["novels"]),
                    "chapters_count": len(validation["chapters"]),
                    "fox_count": len(validation["fox"]),
                    "warnings": validation["warnings"][:100],
                    "error_message": "\n".join(validation["errors"][:30]),
                },
            )
            return JSONResponse(
                {
                    "status": "error",
                    "sync_id": sync_id,
                    "stage": "validation",
                    "errors_count": len(validation["errors"]),
                    "errors": validation["errors"][:100],
                    "warnings_count": len(validation["warnings"]),
                    "warnings": validation["warnings"][:100],
                },
                status_code=400,
            )

        novels = validation["novels"]
        chapters = validation["chapters"]
        fox_rows = validation["fox"]
        warnings = validation["warnings"]

        result: dict[str, Any] = {
            "status": "ok",
            "sync_id": sync_id,
            "source": validation["source"],
            "schema_version": validation["schema_version"],
            "novels_received": len(novels),
            "chapters_received": len(chapters),
            "fox_received": len(fox_rows),
            "novels_upserted": 0,
            "chapters_upserted": 0,
            "fox_upserted": 0,
            "warnings_count": len(warnings),
            "warnings": warnings[:100],
        }

        stage = "novels"
        if novels:
            result["novels_upserted"] = db_upsert("novels", novels, "novel_id", batch_size=50)

        stage = "chapters"
        if chapters:
            result["chapters_upserted"] = db_upsert("chapters", chapters, "chapter_id", batch_size=100)

        stage = "fox"
        if fox_rows:
            result["fox_upserted"] = db_upsert("fox", fox_rows, "name", batch_size=50)

        result["cache_cleared"] = {
            "catalog": clear_catalog_cache(),
            "telegraph": clear_telegraph_cache(),
            "images": clear_image_cache(),
        }

        _finish_sync_run(
            sync_id,
            {
                "status": "ok",
                "novels_count": len(novels),
                "chapters_count": len(chapters),
                "fox_count": len(fox_rows),
                "warnings": warnings[:100],
                "error_message": None,
            },
        )

        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as error:
        print("MiniApp sync failed at stage:", stage)
        traceback.print_exc()
        _finish_sync_run(
            sync_id,
            {
                "status": "error",
                "warnings": [],
                "error_message": f"{stage}: {error}",
            },
        )
        return JSONResponse({"status": "error", "sync_id": sync_id, "stage": stage, "detail": str(error)}, status_code=500)
