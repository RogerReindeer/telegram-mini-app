"""Single source of truth for catalog/sync row shapes shared by services.

``services/catalog.py`` (read path) and ``services/sync.py`` (write path) both
normalize the same spreadsheet-derived rows. Keeping the column allowlists,
header aliases and fox-name normalization here prevents the two call sites
from silently drifting apart (they previously kept separate copies that had
already diverged: sync.py's fox alias table was missing several entries that
catalog.py had, so a messy spreadsheet fox name could be stored under one key
by sync and displayed under a different, unmatched key by the reader).

``normalize_novel_row``/``normalize_chapter_row``/``normalize_fox_row`` and
``filter_columns`` stay in the two call sites on purpose: sync.py must keep
``__sheet_name``/``__row_number`` diagnostics metadata on the row so a failed
upsert can be traced back to a spreadsheet cell, while catalog.py's read path
has no use for that metadata.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..utils import clean_value

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


def normalize_text_list(value: Any) -> list[str]:
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


def parse_iso_datetime(value: Any) -> datetime | None:
    from .reader import parse_date

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
