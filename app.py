import os
import re
import html
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


load_dotenv()

APP_TITLE = "Зефиркины баоцзы"

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_KEY")
    or ""
)
SYNC_TOKEN = os.getenv("SYNC_TOKEN") or ""

NOVEL_TABLE_COLUMNS = {
    "id",
    "slug",
    "title",
    "title_en",
    "post_icons",
    "cover_url",
    "description",
    "tags",
    "top_description",
    "bottom_description",
    "original_language",
    "total_chapters",
    "translated_chapters",
    "progress_percent",
    "status",
    "access_model",
    "schedule_mode",
    "early_access_mode",
    "sort_order",
    "is_visible",
    "age_rating",
    "has_adult_badge",
    "translation_status",
    "translation_status_label",
    "translation_status_color",
    "relation_type",
    "relation_icon",
    "relation_color",
    "tags_short",
    "tags_tooltip",
    "added_date",
    "translation_author",
}

CHAPTER_TABLE_COLUMNS = {
    "chapter_id",
    "novel_id",
    "chapter_no",
    "title",
    "slug",
    "volume",
    "volume_no",
    "volume_title",
    "translation_date",
    "release_date",
    "free_release_date",
    "premium_release_date",
    "telegraph_url",
    "telegraph_free_url",
    "telegraph_premium_url",
    "telegraph_free_code",
    "telegraph_premium_code",
    "source_type",
    "access_level",
    "is_visible",
    "sort_order",
}

FOX_TABLE_COLUMNS = {
    "name",
    "url",
}

KEY_MAP_NOVEL = {
    "NovelID": "id",
    "Slug": "slug",
    "Title": "title",
    "TitleEN": "title_en",
    "PostIcons": "post_icons",
    "CoverURL": "cover_url",
    "Description": "description",
    "Tags": "tags",
    "TopDescription": "top_description",
    "BottomDescription": "bottom_description",
    "OriginalLanguage": "original_language",
    "TotalChapters": "total_chapters",
    "TranslatedChapters": "translated_chapters",
    "ProgressPercent": "progress_percent",
    "Status": "status",
    "AccessModel": "access_model",
    "ScheduleMode": "schedule_mode",
    "EarlyAccessMode": "early_access_mode",
    "SortOrder": "sort_order",
    "IsVisible": "is_visible",
    "AgeRating": "age_rating",
    "HasAdultBadge": "has_adult_badge",
    "TranslationStatus": "translation_status",
    "TranslationStatusLabel": "translation_status_label",
    "TranslationStatusColor": "translation_status_color",
    "RelationType": "relation_type",
    "RelationIcon": "relation_icon",
    "RelationColor": "relation_color",
    "TagsShort": "tags_short",
    "TagsTooltip": "tags_tooltip",
    "AddedDate": "added_date",
    "TranslationAuthor": "translation_author",
}

KEY_MAP_CHAPTER = {
    "ChapterID": "chapter_id",
    "NovelID": "novel_id",
    "ChapterNo": "chapter_no",
    "ChapterTitle": "title",
    "Slug": "slug",
    "Volume": "volume",
    "VolumeNo": "volume_no",
    "VolumeTitle": "volume_title",
    "TranslationDate": "translation_date",
    "ReleaseDate": "release_date",
    "FreeReleaseDate": "free_release_date",
    "PremiumReleaseDate": "premium_release_date",
    "TelegraphURL": "telegraph_url",
    "TelegraphFreeURL": "telegraph_free_url",
    "TelegraphPremiumURL": "telegraph_premium_url",
    "TelegraphFreeCode": "telegraph_free_code",
    "TelegraphPremiumCode": "telegraph_premium_code",
    "SourceType": "source_type",
    "AccessLevel": "access_level",
    "IsVisible": "is_visible",
    "SortOrder": "sort_order",
}

KEY_MAP_FOX = {
    "Name": "name",
    "name": "name",
    "URL": "url",
    "Url": "url",
    "url": "url",
}


app = FastAPI(title="Zefirki Reader Mini App")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def clean_value(value: Any) -> str:
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in ("nan", "none", "null", "undefined"):
        return ""

    return value


def normalize_slug(value: Any) -> str:
    value = clean_value(value).lower()
    value = value.replace("ё", "е")
    value = re.sub(r"[^\wа-яА-Я-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-+", "-", value)
    value = value.strip("-")

    return value


def to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default

    if isinstance(value, bool):
        return int(value)

    text = clean_value(value)

    if not text:
        return default

    text = text.replace("%", "").replace(",", ".")

    try:
        return int(float(text))
    except ValueError:
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default

    text = clean_value(value)

    if not text:
        return default

    text = text.replace("%", "").replace(",", ".")

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


def normalize_progress_percent(value: Any) -> float | int:
    progress = to_float(value, 0.0)

    while progress > 100:
        progress = progress / 100

    if progress < 0:
        return 0

    if progress > 100:
        return 100

    if progress.is_integer():
        return int(progress)

    return round(progress, 1)


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def parse_date(value: Any) -> str:
    text = clean_value(value)

    if not text:
        return ""

    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text

    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    return text


def is_date_open(value: Any) -> bool:
    date_text = parse_date(value)

    if not date_text:
        return False

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text):
        return True

    return date_text <= today_iso()


def split_tags(tags: Any) -> list[str]:
    text = clean_value(tags)

    if not text:
        return []

    parts = re.split(r"[;,\n]+", text)
    result = []

    for part in parts:
        tag = clean_value(part)

        if tag:
            result.append(tag)

    return result


def compact_title_with_icons(post_icons: Any, title: Any) -> str:
    title_text = clean_value(title)
    icons = clean_value(post_icons)

    if not title_text:
        return ""

    if not icons:
        return title_text

    if title_text.startswith(icons):
        return title_text

    return f"{icons} {title_text}"


def supabase_ready() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_headers(prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def supabase_request(
    method: str,
    table: str,
    params: dict[str, Any] | None = None,
    payload: Any | None = None,
    prefer: str | None = None,
) -> Any:
    if not supabase_ready():
        raise RuntimeError("Supabase env vars are not configured")

    url = f"{SUPABASE_URL}/rest/v1/{table}"

    response = requests.request(
        method=method,
        url=url,
        headers=supabase_headers(prefer=prefer),
        params=params or {},
        json=payload,
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Supabase error {response.status_code}: {response.text}"
        )

    if not response.text:
        return None

    try:
        return response.json()
    except ValueError:
        return response.text


def db_select(
    table: str,
    select: str = "*",
    filters: dict[str, str] | None = None,
    order: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    params: dict[str, Any] = {
        "select": select,
    }

    if filters:
        params.update(filters)

    if order:
        params["order"] = order

    if limit:
        params["limit"] = limit

    result = supabase_request("GET", table, params=params)

    if isinstance(result, list):
        return result

    return []


def db_upsert(
    table: str,
    rows: list[dict],
    conflict_key: str,
) -> list[dict]:
    if not rows:
        return []

    result = supabase_request(
        "POST",
        table,
        params={"on_conflict": conflict_key},
        payload=rows,
        prefer="resolution=merge-duplicates,return=representation",
    )

    if isinstance(result, list):
        return result

    return []


def tag_class_name(tag: str) -> str:
    text = clean_value(tag).replace("!", "").lower()

    if text in ("гет", "het"):
        return "tag-get"

    if text in ("слэш", "slash", "bl", "бл", "данмэй"):
        return "tag-slash"

    if text in ("джен", "gen", "нет любовной линии"):
        return "tag-gen"

    if text in ("китай", "корея", "япония"):
        return "tag-country"

    if text in ("g", "pg", "pg-13", "r", "16+", "18+", "21+", "nc-17"):
        return "tag-rating"

    if text in ("сянься/уся", "уся/сянься", "фэнтези", "романтика", "приключения"):
        return "tag-genre"

    return ""


def prepare_tag_items(tags: str) -> list[dict]:
    result = []

    for raw_tag in split_tags(tags):
        text = clean_value(raw_tag)
        is_spoiler = text.startswith("!")
        shown_text = text[1:].strip() if is_spoiler else text

        if not shown_text:
            continue

        result.append(
            {
                "text": shown_text,
                "raw_text": text,
                "is_spoiler": is_spoiler,
                "class_name": tag_class_name(shown_text),
            }
        )

    return result


def normalize_tag_text_for_priority(tag: Any) -> str:
    return clean_value(tag).replace("!", "").strip().lower()


def is_age_rating_tag(tag: Any) -> bool:
    normalized = normalize_tag_text_for_priority(tag)

    return normalized in (
        "g",
        "pg",
        "pg-13",
        "r",
        "r18",
        "r-18",
        "nc-17",
        "16+",
        "18+",
        "21+",
    )


def get_age_rating_from_tags(tags: str) -> str:
    for raw_tag in split_tags(tags):
        normalized = normalize_tag_text_for_priority(raw_tag)

        if normalized == "g":
            return "G"

        if normalized == "pg":
            return "PG"

        if normalized == "pg-13":
            return "PG-13"

        if normalized in ("r18", "r-18", "18+"):
            return "18+"

        if normalized == "16+":
            return "16+"

        if normalized == "21+":
            return "21+"

        if normalized == "nc-17":
            return "NC-17"

        if normalized == "r":
            return "R"

    return ""


def is_card_hidden_tag(tag: Any) -> bool:
    normalized = normalize_tag_text_for_priority(tag)

    hidden_tags = {
        "s",
        "m",
        "l",
        "мини",
        "миди",
        "макси",
        "💙",
        "❤️",
        "💚",
        "✅",
        "🛠",
        "⏳",
        "🟢",
        "🟡",
        "🔴",
        "🎁",
        "📗",
        "📖",
        "завершена",
        "завершено",
        "в процессе перевода",
        "переводится",
        "на передержке",
        "скоро",
        "часть платно",
        "частично платно",
        "платно",
        "boosty only",
    }

    return normalized in hidden_tags


def tag_priority_score(tag: dict) -> int:
    text = normalize_tag_text_for_priority(tag.get("text"))

    if tag.get("is_spoiler"):
        return 999

    if is_age_rating_tag(text):
        return 998

    relation_tags = {
        "гет": 1,
        "слэш": 1,
        "bl": 1,
        "бл": 1,
        "данмэй": 1,
        "джен": 1,
        "нет любовной линии": 1,
    }

    country_tags = {
        "китай": 2,
        "корея": 2,
        "япония": 2,
        "англия": 2,
        "сша": 2,
    }

    pov_tags = {
        "pov героини": 3,
        "pov героя": 3,
        "pov пассива": 3,
        "pov актива": 3,
    }

    genre_tags = {
        "сянься/уся": 4,
        "уся/сянься": 4,
        "фэнтези": 4,
        "романтика": 4,
        "приключения": 4,
        "юмор": 4,
        "детектив": 4,
        "мистика/оккультизм": 4,
        "магия": 4,
        "звери": 4,
        "зверолюди/оборотни": 4,
        "реинкарнация/возрождение": 4,
        "здоровые отношения": 4,
    }

    if text in relation_tags:
        return relation_tags[text]

    if text in country_tags:
        return country_tags[text]

    if text in pov_tags:
        return pov_tags[text]

    if text in genre_tags:
        return genre_tags[text]

    return 50


def build_card_tag_items(tag_items: list[dict]) -> list[dict]:
    card_tag_items = []
    seen = set()

    for item in tag_items:
        text = clean_value(item.get("text"))

        if not text:
            continue

        if item.get("is_spoiler"):
            continue

        if is_age_rating_tag(text):
            continue

        if is_card_hidden_tag(text):
            continue

        normalized = normalize_tag_text_for_priority(text)

        if normalized in seen:
            continue

        seen.add(normalized)
        card_tag_items.append(item)

    card_tag_items = sorted(
        card_tag_items,
        key=lambda item: (
            tag_priority_score(item),
            clean_value(item.get("text")).lower(),
        ),
    )

    return card_tag_items


def normalize_translation_status(raw_status: Any, raw_label: Any = "") -> str:
    text = f"{clean_value(raw_status)} {clean_value(raw_label)}".lower()

    if any(marker in text for marker in ("completed", "complete", "done", "заверш", "✅", "готов")):
        return "completed"

    if any(marker in text for marker in ("paused", "pause", "hold", "передерж", "пауза", "⏳")):
        return "paused"

    if any(marker in text for marker in ("soon", "анонс", "скоро")):
        return "soon"

    return "in_progress"


def translation_status_label(status: str, fallback: Any = "") -> str:
    fallback_text = clean_value(fallback)

    if fallback_text:
        return fallback_text

    labels = {
        "completed": "Завершено",
        "paused": "На передержке",
        "soon": "Скоро",
        "in_progress": "В процессе перевода",
    }

    return labels.get(status, "В процессе перевода")


def translation_status_color(status: str, fallback: Any = "") -> str:
    fallback_text = clean_value(fallback)

    if fallback_text:
        return fallback_text

    colors = {
        "completed": "#44bb44",
        "paused": "#f59e0b",
        "soon": "#4f7cff",
        "in_progress": "#7c5cff",
    }

    return colors.get(status, "#7c5cff")


def build_access_badge(access_model: Any, early_access_mode: Any = "") -> dict | None:
    text = f"{clean_value(access_model)} {clean_value(early_access_mode)}".lower()

    if not text.strip():
        return None

    if "boosty" in text or "boostyonly" in text or "🎁" in text:
        return {
            "icon": "🎁",
            "label": "Boosty only",
            "class_name": "access-boosty",
        }

    if "mini" in text or "🧲" in text:
        return {
            "icon": "🔴",
            "label": "Платно",
            "class_name": "access-paid",
        }

    if "auto" in text or "early" in text or "⏰" in text:
        return {
            "icon": "🟡",
            "label": "Часть платно",
            "class_name": "access-partial",
        }

    if "core" in text or "🌷" in text:
        return {
            "icon": "🟢",
            "label": "Через 🌱",
            "class_name": "access-core",
        }

    return {
        "icon": "🟡",
        "label": "Часть платно",
        "class_name": "access-partial",
    }


def parse_chapter_no_number(value: Any) -> float:
    text = clean_value(value)

    if not text:
        return 0.0

    text = text.replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)

    if not match:
        return 0.0

    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def normalize_chapter_no_for_unit(value: Any) -> str:
    text = clean_value(value)

    if not text:
        return ""

    text = text.replace(",", ".").strip()
    lowered = text.lower()

    patterns = [
        r"^(\d+)[-–—_]\d+$",
        r"^(\d+)\.\d+$",
        r"^(\d+)\s*(?:часть|ч\.|part)\s*\d+$",
        r"^глава\s*(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)

        if match:
            return match.group(1)

    match = re.search(r"\d+", text)

    if match:
        return match.group(0)

    return text.lower()


def chapter_unit_key(chapter: dict) -> str:
    novel_id = clean_value(chapter.get("novel_id"))
    chapter_no = normalize_chapter_no_for_unit(chapter.get("chapter_no"))

    if chapter_no:
        return f"{novel_id}:{chapter_no}"

    chapter_id = clean_value(chapter.get("chapter_id"))

    return f"{novel_id}:{chapter_id}"


def chapter_has_readable_url(chapter: dict) -> bool:
    return bool(
        clean_value(chapter.get("telegraph_url"))
        or clean_value(chapter.get("telegraph_free_url"))
        or clean_value(chapter.get("telegraph_premium_url"))
    )


def chapter_is_available(chapter: dict) -> bool:
    if chapter.get("is_visible") is not True:
        return False

    if not chapter_has_readable_url(chapter):
        return False

    access_level = clean_value(chapter.get("access_level")).lower()

    return access_level in ("public", "subscriber", "premium", "paid", "early")


def count_chapter_units_for_card(chapters: list[dict]) -> int:
    units = set()

    for chapter in chapters:
        units.add(chapter_unit_key(chapter))

    return len(units)


def count_available_chapter_units(chapters: list[dict]) -> int:
    units = set()

    for chapter in chapters:
        if chapter_is_available(chapter):
            units.add(chapter_unit_key(chapter))

    return len(units)


def choose_chapter_url(chapter: dict) -> str:
    access_level = clean_value(chapter.get("access_level")).lower()

    if access_level == "public":
        return (
            clean_value(chapter.get("telegraph_free_url"))
            or clean_value(chapter.get("telegraph_url"))
            or clean_value(chapter.get("telegraph_premium_url"))
        )

    return (
        clean_value(chapter.get("telegraph_premium_url"))
        or clean_value(chapter.get("telegraph_url"))
        or clean_value(chapter.get("telegraph_free_url"))
    )


def prepare_chapter_for_template(chapter: dict) -> dict:
    prepared = dict(chapter)

    prepared["id"] = clean_value(chapter.get("chapter_id"))
    prepared["chapter_id"] = clean_value(chapter.get("chapter_id"))
    prepared["chapter_no"] = clean_value(chapter.get("chapter_no"))
    prepared["title"] = clean_value(chapter.get("title")) or f"Глава {prepared['chapter_no']}"
    prepared["display_title"] = prepared["title"]
    prepared["url"] = choose_chapter_url(chapter)
    prepared["is_available"] = chapter_is_available(chapter)

    access_level = clean_value(chapter.get("access_level")).lower()

    if access_level == "public":
        prepared["access_label"] = "🌱 Открыта"
        prepared["access_class"] = "chapter-access-public"
    elif access_level in ("subscriber", "premium", "paid", "early"):
        prepared["access_label"] = "📜 Для подписчиков"
        prepared["access_class"] = "chapter-access-locked"
    else:
        prepared["access_label"] = "Закрыта"
        prepared["access_class"] = "chapter-access-hidden"

    prepared["sort_value"] = to_float(
        chapter.get("sort_order"),
        parse_chapter_no_number(chapter.get("chapter_no")),
    )

    return prepared


def sort_chapters(chapters: list[dict]) -> list[dict]:
    return sorted(
        chapters,
        key=lambda chapter: (
            to_float(chapter.get("sort_order"), parse_chapter_no_number(chapter.get("chapter_no"))),
            parse_chapter_no_number(chapter.get("chapter_no")),
            clean_value(chapter.get("chapter_id")),
        ),
    )


def build_chapter_display_list(chapters: list[dict]) -> tuple[list[dict], int]:
    prepared = [
        prepare_chapter_for_template(chapter)
        for chapter in sort_chapters(chapters)
        if chapter.get("is_visible") is True
    ]

    paid_seen = 0
    hidden_subscriber_count = 0

    for chapter in prepared:
        access_level = clean_value(chapter.get("access_level")).lower()
        is_paid = access_level in ("subscriber", "premium", "paid", "early")

        chapter["is_paid_extra"] = False

        if is_paid:
            paid_seen += 1

            if paid_seen > 3:
                chapter["is_paid_extra"] = True
                chapter["hidden"] = True
                hidden_subscriber_count += 1

    return prepared, hidden_subscriber_count


def get_chapter_index_info(chapters: list[dict], current_chapter_id: str) -> dict:
    sorted_visible = [
        prepare_chapter_for_template(chapter)
        for chapter in sort_chapters(chapters)
        if chapter_is_available(chapter)
    ]

    units = []
    seen_units = set()

    for chapter in sorted_visible:
        key = chapter_unit_key(chapter)

        if key not in seen_units:
            seen_units.add(key)
            units.append(
                {
                    "unit_key": key,
                    "chapter_id": chapter.get("chapter_id"),
                    "chapter_title": chapter.get("title"),
                }
            )

    current_index = 0

    for index, unit in enumerate(units, start=1):
        if clean_value(unit.get("chapter_id")) == clean_value(current_chapter_id):
            current_index = index
            break

    if not current_index:
        current_key = ""

        for chapter in sorted_visible:
            if clean_value(chapter.get("chapter_id")) == clean_value(current_chapter_id):
                current_key = chapter_unit_key(chapter)
                break

        if current_key:
            for index, unit in enumerate(units, start=1):
                if unit["unit_key"] == current_key:
                    current_index = index
                    break

    return {
        "chapter_index": current_index,
        "available_chapters": len(units),
    }


def get_neighbor_chapters(chapters: list[dict], current_chapter_id: str) -> tuple[dict | None, dict | None]:
    available = [
        prepare_chapter_for_template(chapter)
        for chapter in sort_chapters(chapters)
        if chapter_is_available(chapter)
    ]

    index = None

    for i, chapter in enumerate(available):
        if clean_value(chapter.get("chapter_id")) == clean_value(current_chapter_id):
            index = i
            break

    if index is None:
        return None, None

    previous_chapter = available[index - 1] if index > 0 else None
    next_chapter = available[index + 1] if index + 1 < len(available) else None

    return previous_chapter, next_chapter


def prepare_novel_for_template(novel: dict) -> dict:
    prepared = dict(novel)

    title = clean_value(novel.get("title"))
    post_icons = clean_value(novel.get("post_icons"))
    tags = clean_value(novel.get("tags"))

    display_title = compact_title_with_icons(post_icons, title)

    tag_items = prepare_tag_items(tags)
    card_tag_items = build_card_tag_items(tag_items)

    translation_status = normalize_translation_status(
        novel.get("translation_status") or novel.get("status"),
        novel.get("translation_status_label"),
    )

    progress_percent = normalize_progress_percent(novel.get("progress_percent"))

    prepared["id"] = clean_value(novel.get("id"))
    prepared["slug"] = clean_value(novel.get("slug")) or normalize_slug(title)
    prepared["title"] = title
    prepared["display_title"] = display_title
    prepared["title_en"] = clean_value(novel.get("title_en"))
    prepared["post_icons"] = post_icons
    prepared["cover_url"] = clean_value(novel.get("cover_url"))
    prepared["description"] = clean_value(novel.get("description"))
    prepared["top_description"] = clean_value(novel.get("top_description"))
    prepared["bottom_description"] = clean_value(novel.get("bottom_description"))
    prepared["tags"] = tags
    prepared["tag_items"] = tag_items
    prepared["catalog_tag_items"] = card_tag_items[:5]
    prepared["card_tag_items"] = card_tag_items[:5]
    prepared["catalog_hidden_tags"] = max(0, len(card_tag_items) - 5)

    prepared["age_rating"] = (
        clean_value(novel.get("age_rating"))
        or get_age_rating_from_tags(tags)
    )

    prepared["has_adult_badge"] = (
        to_bool(novel.get("has_adult_badge"), False)
        or prepared["age_rating"] in ("18+", "21+", "NC-17", "R")
    )

    prepared["total_chapters"] = to_int(novel.get("total_chapters"), 0)
    prepared["translated_chapters"] = to_int(novel.get("translated_chapters"), 0)
    prepared["progress_percent"] = progress_percent
    prepared["normalized_progress_percent"] = progress_percent

    prepared["translation_status"] = translation_status
    prepared["translation_status_label"] = translation_status_label(
        translation_status,
        novel.get("translation_status_label"),
    )
    prepared["translation_status_color"] = translation_status_color(
        translation_status,
        novel.get("translation_status_color"),
    )

    prepared["access_badge"] = build_access_badge(
        novel.get("access_model"),
        novel.get("early_access_mode"),
    )

    prepared["relation_type"] = clean_value(novel.get("relation_type"))
    prepared["relation_icon"] = clean_value(novel.get("relation_icon"))
    prepared["relation_color"] = clean_value(novel.get("relation_color"))

    prepared["sort_order"] = to_float(novel.get("sort_order"), 999999)
    prepared["is_visible"] = to_bool(novel.get("is_visible"), True)
    prepared["added_date"] = parse_date(novel.get("added_date"))
    prepared["translation_author"] = clean_value(novel.get("translation_author"))

    prepared["display_chapters_count"] = to_int(
        novel.get("display_chapters_count"),
        prepared["total_chapters"],
    )
    prepared["available_chapters_count"] = to_int(
        novel.get("available_chapters_count"),
        0,
    )

    return prepared


def attach_chapter_counts_to_novels(
    novels: list[dict],
    chapters: list[dict],
) -> list[dict]:
    chapters_by_novel: dict[str, list[dict]] = {}

    for chapter in chapters:
        novel_id = clean_value(chapter.get("novel_id"))

        if not novel_id:
            continue

        chapters_by_novel.setdefault(novel_id, []).append(chapter)

    result = []

    for novel in novels:
        prepared = prepare_novel_for_template(novel)
        novel_id = clean_value(prepared.get("id"))
        novel_chapters = chapters_by_novel.get(novel_id, [])

        display_chapters_count = count_chapter_units_for_card(novel_chapters)
        available_chapters_count = count_available_chapter_units(novel_chapters)

        prepared["display_chapters_count"] = display_chapters_count or prepared["total_chapters"] or 0
        prepared["available_chapters_count"] = available_chapters_count

        result.append(prepared)

    return result


def telegraph_path_from_url(url: str) -> str:
    text = clean_value(url)

    if not text:
        return ""

    text = text.split("?")[0].rstrip("/")

    if "telegra.ph/" in text:
        return text.split("telegra.ph/", 1)[1]

    if "teletype.in/" in text:
        return ""

    return text


def render_telegraph_node(node: Any) -> str:
    if isinstance(node, str):
        return html.escape(node)

    if not isinstance(node, dict):
        return ""

    tag = clean_value(node.get("tag"))

    if not tag:
        return ""

    attrs = node.get("attrs") or {}
    children = node.get("children") or []

    safe_attrs = []

    if isinstance(attrs, dict):
        for key, value in attrs.items():
            key_text = clean_value(key)
            value_text = clean_value(value)

            if key_text in ("href", "src", "alt", "title"):
                safe_attrs.append(
                    f'{html.escape(key_text)}="{html.escape(value_text)}"'
                )

    attrs_text = f" {' '.join(safe_attrs)}" if safe_attrs else ""
    inner = "".join(render_telegraph_node(child) for child in children)

    if tag in ("br", "img"):
        return f"<{tag}{attrs_text}>"

    return f"<{tag}{attrs_text}>{inner}</{tag}>"


def fetch_telegraph_content(url: str) -> tuple[dict | None, str]:
    path = telegraph_path_from_url(url)

    if not path:
        return None, ""

    api_url = f"https://api.telegra.ph/getPage/{quote(path)}"

    try:
        response = requests.get(
            api_url,
            params={"return_content": "true"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        return None, f"Ошибка загрузки Telegraph: {error}"

    if not data.get("ok"):
        return None, data.get("error") or "Telegraph вернул ошибку."

    result = data.get("result") or {}
    content = result.get("content") or []
    html_content = "".join(render_telegraph_node(node) for node in content)

    return {
        "title": result.get("title") or "",
        "content_html": html_content,
    }, ""


def normalize_dict_keys(row: dict, key_map: dict[str, str]) -> dict:
    normalized = {}

    for key, value in row.items():
        mapped_key = key_map.get(key, key)
        normalized[mapped_key] = value

    return normalized


def filter_columns(row: dict, allowed_columns: set[str]) -> dict:
    return {
        key: value
        for key, value in row.items()
        if key in allowed_columns
    }


def normalize_novel_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_NOVEL)

    title = clean_value(row.get("title"))

    row["id"] = clean_value(row.get("id"))

    if not row["id"]:
        row["id"] = clean_value(row.get("novel_id"))

    row["slug"] = clean_value(row.get("slug")) or normalize_slug(title or row["id"])
    row["title"] = title
    row["title_en"] = clean_value(row.get("title_en"))
    row["post_icons"] = clean_value(row.get("post_icons"))
    row["cover_url"] = clean_value(row.get("cover_url"))
    row["description"] = clean_value(row.get("description"))
    row["tags"] = clean_value(row.get("tags"))
    row["top_description"] = clean_value(row.get("top_description"))
    row["bottom_description"] = clean_value(row.get("bottom_description"))
    row["original_language"] = clean_value(row.get("original_language"))

    row["total_chapters"] = to_int(row.get("total_chapters"), 0)
    row["translated_chapters"] = to_int(row.get("translated_chapters"), 0)
    row["progress_percent"] = normalize_progress_percent(row.get("progress_percent"))

    row["translation_status"] = normalize_translation_status(
        row.get("translation_status") or row.get("status"),
        row.get("translation_status_label"),
    )
    row["translation_status_label"] = translation_status_label(
        row["translation_status"],
        row.get("translation_status_label"),
    )
    row["translation_status_color"] = translation_status_color(
        row["translation_status"],
        row.get("translation_status_color"),
    )

    row["status"] = clean_value(row.get("status"))
    row["access_model"] = clean_value(row.get("access_model"))
    row["schedule_mode"] = clean_value(row.get("schedule_mode"))
    row["early_access_mode"] = clean_value(row.get("early_access_mode"))

    row["sort_order"] = to_float(row.get("sort_order"), to_float(row.get("id"), 999999))
    row["is_visible"] = to_bool(row.get("is_visible"), True)
    row["age_rating"] = clean_value(row.get("age_rating")) or get_age_rating_from_tags(row["tags"])
    row["has_adult_badge"] = (
        to_bool(row.get("has_adult_badge"), False)
        or row["age_rating"] in ("18+", "21+", "NC-17", "R")
    )

    row["relation_type"] = clean_value(row.get("relation_type"))
    row["relation_icon"] = clean_value(row.get("relation_icon"))
    row["relation_color"] = clean_value(row.get("relation_color"))
    row["tags_short"] = clean_value(row.get("tags_short"))
    row["tags_tooltip"] = clean_value(row.get("tags_tooltip"))
    row["added_date"] = parse_date(row.get("added_date"))
    row["translation_author"] = clean_value(row.get("translation_author"))

    return filter_columns(row, NOVEL_TABLE_COLUMNS)


def normalize_chapter_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_CHAPTER)

    chapter_id = clean_value(row.get("chapter_id"))
    novel_id = clean_value(row.get("novel_id"))
    chapter_no = clean_value(row.get("chapter_no"))

    if not chapter_id:
        chapter_id = f"{novel_id}-{chapter_no}"

    row["chapter_id"] = chapter_id
    row["novel_id"] = novel_id
    row["chapter_no"] = chapter_no
    row["title"] = clean_value(row.get("title")) or f"Глава {chapter_no}"
    row["slug"] = clean_value(row.get("slug")) or normalize_slug(f"{novel_id}-{chapter_no}-{row['title']}")

    row["volume"] = clean_value(row.get("volume"))
    row["volume_no"] = clean_value(row.get("volume_no"))
    row["volume_title"] = clean_value(row.get("volume_title"))

    row["translation_date"] = parse_date(row.get("translation_date"))
    row["release_date"] = parse_date(row.get("release_date"))
    row["free_release_date"] = parse_date(row.get("free_release_date"))
    row["premium_release_date"] = parse_date(row.get("premium_release_date"))

    row["telegraph_url"] = clean_value(row.get("telegraph_url"))
    row["telegraph_free_url"] = clean_value(row.get("telegraph_free_url"))
    row["telegraph_premium_url"] = clean_value(row.get("telegraph_premium_url"))
    row["telegraph_free_code"] = clean_value(row.get("telegraph_free_code"))
    row["telegraph_premium_code"] = clean_value(row.get("telegraph_premium_code"))

    row["source_type"] = clean_value(row.get("source_type")) or "telegraph"

    access_level = clean_value(row.get("access_level")).lower()

    if not access_level:
        if row["telegraph_free_url"] and is_date_open(row["free_release_date"]):
            access_level = "public"
        elif row["telegraph_premium_url"] or row["telegraph_url"] or row["telegraph_free_url"]:
            access_level = "subscriber"
        else:
            access_level = "hidden"

    row["access_level"] = access_level

    has_any_url = bool(
        row["telegraph_url"]
        or row["telegraph_free_url"]
        or row["telegraph_premium_url"]
    )

    row["is_visible"] = to_bool(row.get("is_visible"), has_any_url)
    row["sort_order"] = to_float(
        row.get("sort_order"),
        parse_chapter_no_number(chapter_no),
    )

    return filter_columns(row, CHAPTER_TABLE_COLUMNS)


def normalize_fox_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_FOX)

    normalized = {
        "name": clean_value(row.get("name")),
        "url": clean_value(row.get("url")),
    }

    return filter_columns(normalized, FOX_TABLE_COLUMNS)


def get_fox() -> dict[str, str]:
    default_fox = {
        "fox_peek": "",
        "fox_pic": "",
        "fox_side": "",
        "fox_sitting_front": "",
    }

    if not supabase_ready():
        return default_fox

    try:
        rows = db_select("fox", select="name,url")
    except Exception:
        return default_fox

    for row in rows:
        name = clean_value(row.get("name"))
        url = clean_value(row.get("url"))

        if name and url:
            default_fox[name] = url

    return default_fox


def get_all_novels(include_hidden: bool = False) -> list[dict]:
    if not supabase_ready():
        return []

    filters = None if include_hidden else {"is_visible": "eq.true"}

    try:
        return db_select(
            "novels",
            select="*",
            filters=filters,
            order="sort_order.asc,id.asc",
        )
    except Exception as error:
        print("get_all_novels error:", error)
        return []


def get_all_chapters() -> list[dict]:
    if not supabase_ready():
        return []

    try:
        return db_select(
            "chapters",
            select="*",
            order="novel_id.asc,sort_order.asc,chapter_no.asc",
        )
    except Exception as error:
        print("get_all_chapters error:", error)
        return []


def get_novel_by_slug(slug: str) -> dict | None:
    if not supabase_ready():
        return None

    rows = db_select(
        "novels",
        select="*",
        filters={
            "slug": f"eq.{slug}",
            "is_visible": "eq.true",
        },
        limit=1,
    )

    if not rows:
        return None

    return rows[0]


def get_novel_chapters(novel_id: str) -> list[dict]:
    if not supabase_ready():
        return []

    return db_select(
        "chapters",
        select="*",
        filters={"novel_id": f"eq.{novel_id}"},
        order="sort_order.asc,chapter_no.asc",
    )


def get_chapter_by_id(chapter_id: str) -> dict | None:
    if not supabase_ready():
        return None

    rows = db_select(
        "chapters",
        select="*",
        filters={"chapter_id": f"eq.{chapter_id}"},
        limit=1,
    )

    if not rows:
        return None

    return rows[0]


def get_novel_by_id(novel_id: str) -> dict | None:
    if not supabase_ready():
        return None

    rows = db_select(
        "novels",
        select="*",
        filters={"id": f"eq.{novel_id}"},
        limit=1,
    )

    if not rows:
        return None

    return rows[0]


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "supabase": "ok" if supabase_ready() else "not_configured",
    }


@app.get("/")
async def home():
    return RedirectResponse(url="/library")


@app.get("/library")
async def library(request: Request):
    novels = get_all_novels(include_hidden=False)
    chapters = get_all_chapters()
    fox = get_fox()

    prepared_novels = attach_chapter_counts_to_novels(novels, chapters)

    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "app_title": APP_TITLE,
            "novels": prepared_novels,
            "fox": fox,
        },
    )


@app.get("/novel/{slug}")
async def novel_page(request: Request, slug: str):
    novel = get_novel_by_slug(slug)

    if not novel:
        raise HTTPException(status_code=404, detail="Новелла не найдена")

    fox = get_fox()
    all_chapters = get_novel_chapters(clean_value(novel.get("id")))

    prepared_novel = prepare_novel_for_template(novel)

    prepared_novel["display_chapters_count"] = (
        count_chapter_units_for_card(all_chapters)
        or prepared_novel["total_chapters"]
        or 0
    )
    prepared_novel["available_chapters_count"] = count_available_chapter_units(all_chapters)

    visible_chapters = [
        chapter
        for chapter in all_chapters
        if chapter.get("is_visible") is True
    ]

    display_chapters, hidden_subscriber_count = build_chapter_display_list(visible_chapters)

    return templates.TemplateResponse(
        request,
        "novel.html",
        {
            "app_title": APP_TITLE,
            "novel": prepared_novel,
            "chapters": display_chapters,
            "display_chapters": display_chapters,
            "hidden_subscriber_count": hidden_subscriber_count,
            "fox": fox,
        },
    )


@app.get("/chapter/{chapter_id}")
async def chapter_page(request: Request, chapter_id: str):
    chapter = get_chapter_by_id(chapter_id)

    if not chapter:
        raise HTTPException(status_code=404, detail="Глава не найдена")

    novel = get_novel_by_id(clean_value(chapter.get("novel_id")))

    if not novel:
        raise HTTPException(status_code=404, detail="Книга главы не найдена")

    all_chapters = get_novel_chapters(clean_value(novel.get("id")))
    prepared_chapter = prepare_chapter_for_template(chapter)
    prepared_novel = prepare_novel_for_template(novel)

    previous_chapter, next_chapter = get_neighbor_chapters(
        all_chapters,
        clean_value(chapter.get("chapter_id")),
    )

    index_info = get_chapter_index_info(
        all_chapters,
        clean_value(chapter.get("chapter_id")),
    )

    url = choose_chapter_url(chapter)
    is_locked = not prepared_chapter["is_available"]

    telegraph_content = None
    telegraph_error = ""

    if url and not is_locked:
        telegraph_content, telegraph_error = fetch_telegraph_content(url)

    fox = get_fox()

    return templates.TemplateResponse(
        request,
        "chapter.html",
        {
            "app_title": APP_TITLE,
            "chapter": prepared_chapter,
            "novel": prepared_novel,
            "previous_chapter": previous_chapter,
            "next_chapter": next_chapter,
            "chapter_index": index_info["chapter_index"],
            "available_chapters": index_info["available_chapters"],
            "is_locked": is_locked,
            "telegraph_content": telegraph_content,
            "telegraph_error": telegraph_error,
            "fox": fox,
        },
    )


@app.get("/api/library")
async def api_library():
    novels = get_all_novels(include_hidden=False)
    chapters = get_all_chapters()

    prepared_novels = attach_chapter_counts_to_novels(novels, chapters)

    return {
        "status": "ok",
        "novels_count": len(prepared_novels),
        "chapters_count_sample": len(chapters),
        "novels_sample": prepared_novels,
    }


@app.get("/api/novel/{slug}")
async def api_novel(slug: str):
    novel = get_novel_by_slug(slug)

    if not novel:
        raise HTTPException(status_code=404, detail="Новелла не найдена")

    chapters = get_novel_chapters(clean_value(novel.get("id")))

    return {
        "status": "ok",
        "novel": prepare_novel_for_template(novel),
        "chapters": [prepare_chapter_for_template(chapter) for chapter in chapters],
    }


def validate_sync_token(request: Request, token: str | None) -> None:
    if not SYNC_TOKEN:
        return

    header_token = request.headers.get("x-sync-token") or request.headers.get("X-Sync-Token")
    bearer = request.headers.get("authorization") or request.headers.get("Authorization") or ""

    if bearer.lower().startswith("bearer "):
        bearer = bearer[7:].strip()

    received = token or header_token or bearer

    if received != SYNC_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный sync token")


@app.post("/sync")
async def sync_from_sheets(
    request: Request,
    token: str | None = Query(default=None),
):
    validate_sync_token(request, token)

    if not supabase_ready():
        raise HTTPException(status_code=500, detail="Supabase env vars are not configured")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ожидался JSON")

    novels_raw = payload.get("novels") or payload.get("Novels") or []
    chapters_raw = payload.get("chapters") or payload.get("Chapters") or []
    fox_raw = payload.get("fox") or payload.get("Fox") or []

    if isinstance(novels_raw, dict):
        novels_raw = list(novels_raw.values())

    if isinstance(chapters_raw, dict):
        chapters_raw = list(chapters_raw.values())

    if isinstance(fox_raw, dict):
        fox_raw = list(fox_raw.values())

    novels = [
        normalize_novel_row(row)
        for row in novels_raw
        if isinstance(row, dict)
    ]

    chapters = [
        normalize_chapter_row(row)
        for row in chapters_raw
        if isinstance(row, dict)
    ]

    fox_rows = [
        normalize_fox_row(row)
        for row in fox_raw
        if isinstance(row, dict)
    ]

    novels = [
        row for row in novels
        if clean_value(row.get("id")) and clean_value(row.get("title"))
    ]

    chapters = [
        row for row in chapters
        if clean_value(row.get("chapter_id")) and clean_value(row.get("novel_id"))
    ]

    fox_rows = [
        row for row in fox_rows
        if clean_value(row.get("name")) and clean_value(row.get("url"))
    ]

    result = {
        "status": "ok",
        "novels_received": len(novels),
        "chapters_received": len(chapters),
        "fox_received": len(fox_rows),
        "novels_upserted": 0,
        "chapters_upserted": 0,
        "fox_upserted": 0,
    }

    if novels:
        upserted_novels = db_upsert("novels", novels, "id")
        result["novels_upserted"] = len(upserted_novels)

    if chapters:
        upserted_chapters = db_upsert("chapters", chapters, "chapter_id")
        result["chapters_upserted"] = len(upserted_chapters)

    if fox_rows:
        upserted_fox = db_upsert("fox", fox_rows, "name")
        result["fox_upserted"] = len(upserted_fox)

    return result


@app.post("/api/sync")
async def sync_from_sheets_alias(
    request: Request,
    token: str | None = Query(default=None),
):
    return await sync_from_sheets(request, token)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_title": APP_TITLE,
            "error": "Страница не найдена.",
        },
        status_code=404,
    )
