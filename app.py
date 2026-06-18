import csv
import os
import re
import time
from datetime import datetime
from io import StringIO
from urllib.parse import urlparse, quote

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

MINIAPP_SHEET_ID = os.getenv(
    "MINIAPP_SHEET_ID",
    "1-dHdJEnBai_ZAcdZKwgTryoQ-uAfSgP52qTnbU4amHs",
)

SYNC_TOKEN = os.getenv("SYNC_TOKEN")

SHEET_CACHE_TTL_SECONDS = 300

app = FastAPI(title="Zefirki Reader Mini App")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SHEET_CACHE = {}


def mask_env_value(value: str | None):
    if value is None:
        return {
            "exists": False,
            "length": 0,
            "prefix": None,
            "has_extra_spaces": False,
            "has_quotes": False,
        }

    return {
        "exists": True,
        "length": len(value),
        "prefix": value[:12],
        "has_extra_spaces": value.strip() != value,
        "has_quotes": (
            value.startswith('"')
            or value.endswith('"')
            or value.startswith("'")
            or value.endswith("'")
        ),
    }


def validate_env_value(name: str, value: str | None):
    if not value:
        raise RuntimeError(f"{name} is not set")

    if value.strip() != value:
        raise RuntimeError(f"{name} has extra spaces at the beginning or end")

    if (
        value.startswith('"')
        or value.endswith('"')
        or value.startswith("'")
        or value.endswith("'")
    ):
        raise RuntimeError(f"{name} must not include quotes")


def validate_required_env_for_admin_sync():
    validate_env_value("SUPABASE_URL", SUPABASE_URL)
    validate_env_value("SUPABASE_SERVICE_KEY", SUPABASE_SERVICE_KEY)
    validate_env_value("MINIAPP_SHEET_ID", MINIAPP_SHEET_ID)
    validate_env_value("SYNC_TOKEN", SYNC_TOKEN)

    if "supabase.co" not in SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL does not look like a Supabase project URL")


def make_error_response(error: Exception, status_code: int = 500):
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "type": error.__class__.__name__,
            "message": str(error),
        },
    )


def get_supabase() -> Client:
    validate_env_value("SUPABASE_URL", SUPABASE_URL)

    key = SUPABASE_SERVICE_KEY or SUPABASE_KEY

    if not key:
        raise RuntimeError("Neither SUPABASE_SERVICE_KEY nor SUPABASE_KEY is set")

    if key.strip() != key:
        raise RuntimeError("Supabase key has extra spaces at the beginning or end")

    if (
        key.startswith('"')
        or key.endswith('"')
        or key.startswith("'")
        or key.endswith("'")
    ):
        raise RuntimeError("Supabase key must not include quotes")

    return create_client(SUPABASE_URL, key)


def get_admin_supabase() -> Client:
    validate_required_env_for_admin_sync()
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def clean_value(value):
    if value is None:
        return ""

    return str(value).strip()


def to_int(value):
    value = clean_value(value)

    if not value:
        return None

    try:
        return int(float(value.replace(",", ".")))
    except ValueError:
        return None


def to_float(value):
    value = clean_value(value).replace("%", "").replace(",", ".")

    if not value:
        return None

    try:
        return float(value)
    except ValueError:
        return None


def normalize_progress_percent(value):
    number = to_float(value)

    if number is None:
        return None

    while number > 100:
        number = number / 100

    if number < 0:
        number = 0

    if number > 100:
        number = 100

    return round(number, 1)


def to_bool(value):
    if value is True:
        return True

    if value is False:
        return False

    value = clean_value(value).lower()

    if not value:
        return False

    return value in (
        "true",
        "1",
        "yes",
        "да",
        "истина",
        "✅",
        "☑",
        "checked",
        "on",
    )


def normalize_date(value):
    value = clean_value(value)

    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            pass

    return None


def format_date_ru(value):
    value = clean_value(value)

    if not value:
        return ""

    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            date = datetime.strptime(value[:10], fmt)
            return date.strftime("%d.%m.%Y")
        except ValueError:
            pass

    return value


def parse_chapter_no_number(value):
    text = clean_value(value).replace(",", ".")

    if not text:
        return None

    direct = to_float(text)

    if direct is not None:
        return direct

    match = re.search(
        r"(\d+)(?:\s*(?:-|\.|/)\s*(?:часть|ч|part|p)?\s*(\d+))?",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    base = int(match.group(1))
    part = match.group(2)

    if part:
        return base + int(part) / 100

    return float(base)


def clean_chapter_title(value):
    text = clean_value(value)

    text = re.sub(r"--+", "", text)
    text = re.sub(r"—\s*—+", "", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_chapter_no_for_unit(value):
    number = to_float(value)

    if number is not None:
        int_part = int(number)

        if int_part > 0:
            return str(int_part)

    text = clean_value(value)

    if not text:
        return ""

    text = text.lower()
    text = text.replace("ё", "е")
    text = text.replace(",", ".")
    text = re.sub(r"\s+", " ", text).strip()

    patterns = [
        r"^(\d+)(?:\s*(?:-|\.|/|_)\s*(?:часть|ч|part|p)?\s*\d+)?$",
        r"^(\d+)\s+(?:часть|ч|part|p)\s*\d+$",
        r"^глава\s*(\d+)(?:\s*(?:-|\.|/|_)\s*(?:часть|ч|part|p)?\s*\d+)?$",
        r"^(\d+)\s*[\(\[]\s*(?:часть|ч|part|p)?\s*\d+\s*[\)\]]$",
    ]

    for pattern in patterns:
        match = re.match(pattern, text, re.IGNORECASE)

        if match:
            return match.group(1)

    match = re.search(r"(\d+)", text)

    if match:
        return match.group(1)

    return text


def chapter_unit_key(chapter: dict):
    chapter_no = normalize_chapter_no_for_unit(chapter.get("chapter_no"))

    if chapter_no:
        return f"chapter-no:{chapter_no}"

    chapter_code = clean_value(chapter.get("chapter_code"))

    if chapter_code:
        return f"chapter-code:{chapter_code}"

    chapter_id = clean_value(chapter.get("id"))

    if chapter_id:
        return f"id:{chapter_id}"

    return ""


def count_chapter_units_for_card(chapters: list[dict]) -> int:
    keys = set()

    for chapter in chapters:
        key = chapter_unit_key(chapter)

        if key:
            keys.add(key)

    return len(keys)


def count_available_chapter_units(chapters: list[dict]) -> int:
    keys = set()

    for chapter in chapters:
        if chapter.get("access_level") not in ("public", "subscriber"):
            continue

        if chapter.get("is_visible") is False:
            continue

        key = chapter_unit_key(chapter)

        if key:
            keys.add(key)

    return len(keys)


def split_tags(tags: str):
    return [
        tag.strip()
        for tag in clean_value(tags).split(";")
        if tag.strip()
    ]


def normalize_tag_for_compare(tag: str):
    return (
        clean_value(tag)
        .replace("!", "")
        .replace("ё", "е")
        .lower()
        .strip()
    )


def normalized_tags(tags: str):
    return [normalize_tag_for_compare(tag) for tag in split_tags(tags)]


def relation_icon_from_tags(tags: str):
    tags_lower = normalized_tags(tags)

    if "гет" in tags_lower:
        return "❤️"

    if (
        "слэш" in tags_lower
        or "bl" in tags_lower
        or "бл" in tags_lower
        or "данмэй" in tags_lower
        or "danmei" in tags_lower
    ):
        return "💙"

    if (
        "джен" in tags_lower
        or "нет любовной линии" in tags_lower
        or "без любовной линии" in tags_lower
    ):
        return "💚"

    return ""


def relation_type_from_tags(tags: str):
    tags_lower = normalized_tags(tags)

    if "гет" in tags_lower:
        return "Гет"

    if (
        "слэш" in tags_lower
        or "bl" in tags_lower
        or "бл" in tags_lower
        or "данмэй" in tags_lower
        or "danmei" in tags_lower
    ):
        return "Слэш"

    if (
        "джен" in tags_lower
        or "нет любовной линии" in tags_lower
        or "без любовной линии" in tags_lower
    ):
        return "Джен"

    return ""


def relation_color_from_type(relation_type: str):
    relation_type = clean_value(relation_type).lower()

    if relation_type == "гет":
        return "#ff4444"

    if relation_type == "слэш":
        return "#4488ff"

    if relation_type == "джен":
        return "#44bb44"

    return ""


def age_rating_from_tags(tags: str):
    tags_lower = normalized_tags(tags)

    for rating in ("18+", "16+", "12+", "6+", "0+"):
        if rating.lower() in tags_lower:
            return rating

    for tag in tags_lower:
        match = re.match(r"^(?:r-?|р-?)?(18|16|12|6|0)\+$", tag)

        if match:
            return f"{match.group(1)}+"

    return ""


def size_meta_from_tags(tags: str):
    tags_lower = normalized_tags(tags)

    if "мини" in tags_lower or "s" in tags_lower:
        return {
            "code": "S",
            "label": "Мини",
        }

    if "миди" in tags_lower or "m" in tags_lower:
        return {
            "code": "M",
            "label": "Миди",
        }

    if "макси" in tags_lower or "l" in tags_lower:
        return {
            "code": "L",
            "label": "Макси",
        }

    return {
        "code": "",
        "label": "",
    }


def access_badge_from_model(access_model: str, early_access_mode: str = ""):
    text = f"{access_model or ''} {early_access_mode or ''}".lower()

    if "boostyonly" in text or "boosty only" in text or "🎁" in text:
        return {
            "icon": "🎁",
            "label": "Boosty only",
            "class_name": "access-boosty",
        }

    if "paid" in text or "плат" in text or "🔴" in text:
        return {
            "icon": "🔴",
            "label": "Платно",
            "class_name": "access-paid",
        }

    if "partial" in text or "част" in text or "early" in text or "⏰" in text or "🟡" in text:
        return {
            "icon": "🟡",
            "label": "Часть платно",
            "class_name": "access-partial",
        }

    if "core" in text or "🌷" in text or "🟢" in text:
        return {
            "icon": "🟢",
            "label": "Через 🌱",
            "class_name": "access-core",
        }

    return {
        "icon": "",
        "label": "",
        "class_name": "",
    }


def translation_meta_from_status(status: str, schedule_mode: str, progress_percent):
    combined = f"{status or ''} {schedule_mode or ''}".lower()
    progress = normalize_progress_percent(progress_percent)

    if (
        "пауз" in combined
        or "передерж" in combined
        or "pause" in combined
        or "paused" in combined
        or "hold" in combined
        or "⏳" in combined
    ):
        return {
            "value": "paused",
            "label": "На передержке",
            "color": "#f2c94c",
            "icon": "⏳",
        }

    if (
        "заверш" in combined
        or "done" in combined
        or "готов" in combined
        or "полностью" in combined
        or "✅" in combined
        or progress == 100
    ):
        return {
            "value": "completed",
            "label": "Завершена",
            "color": "#44bb44",
            "icon": "✅",
        }

    return {
        "value": "in_progress",
        "label": "В процессе перевода",
        "color": "#f59e0b",
        "icon": "🛠",
    }


def translation_status_icon_from_value(value: str):
    value = clean_value(value).lower()

    if value == "completed":
        return "✅"

    if value == "paused":
        return "⏳"

    return "🛠"


def tag_class_for_text(tag: str):
    clean_tag = tag.replace("!", "").strip()
    tag_lower = clean_tag.lower()

    if tag_lower in ("he", "хэ"):
        return "tag-he"

    if tag_lower in ("18+", "16+", "12+", "6+", "0+", "r18", "r-18", "nc-17"):
        return "tag-rating"

    if tag_lower == "гет":
        return "tag-get"

    if tag_lower in ("слэш", "bl", "бл", "данмэй", "danmei"):
        return "tag-slash"

    if tag_lower in ("джен", "нет любовной линии", "без любовной линии"):
        return "tag-gen"

    if tag_lower in ("мини", "миди", "макси"):
        return "tag-size"

    if tag_lower in (
        "китай",
        "корея",
        "япония",
        "англия",
        "сша",
        "en",
        "cn",
        "kor",
        "jp",
    ):
        return "tag-country"

    if "pov" in tag_lower:
        return "tag-pov"

    if tag_lower in ("сянься/уся", "уся/сянься", "фэнтези", "современность", "романтика"):
        return "tag-genre"

    return ""


def prepare_tag_items(tags: str):
    items = []

    for raw_tag in split_tags(tags):
        is_spoiler = raw_tag.startswith("!")
        text = raw_tag[1:].strip() if is_spoiler else raw_tag.strip()

        if not text:
            continue

        if text.upper() == "HE":
            is_spoiler = False
            text = "HE"

        items.append({
            "text": text,
            "is_spoiler": is_spoiler,
            "class_name": tag_class_for_text(raw_tag),
        })

    return items


CARD_TAG_PRIORITY = [
    "гет",
    "слэш",
    "bl",
    "бл",
    "данмэй",
    "danmei",
    "джен",
    "нет любовной линии",
    "китай",
    "корея",
    "япония",
    "мини",
    "миди",
    "макси",
    "pov героини",
    "pov пассива",
    "pov актива",
    "сянься/уся",
    "уся/сянься",
    "фэнтези",
    "современность",
    "романтика",
    "he",
]


def prepare_card_tag_items(tags: str, limit: int = 5):
    source_tags = split_tags(tags)
    prepared = []
    skipped_count = 0
    seen = set()

    def normalize_card_text(raw_tag: str):
        is_spoiler = raw_tag.startswith("!")
        text = raw_tag[1:].strip() if is_spoiler else raw_tag.strip()

        if not text:
            return None

        if is_spoiler and text.upper() != "HE":
            return None

        if text.upper() == "HE":
            return "HE"

        if text.strip().upper() in ("G", "S", "M", "L"):
            return None

        return text

    candidates = []

    for index, raw_tag in enumerate(source_tags):
        text = normalize_card_text(raw_tag)

        if not text:
            skipped_count += 1
            continue

        compare = normalize_tag_for_compare(text)

        if compare in seen:
            continue

        seen.add(compare)

        if compare in CARD_TAG_PRIORITY:
            priority = CARD_TAG_PRIORITY.index(compare)
        else:
            priority = 999 + index

        candidates.append({
            "text": text,
            "compare": compare,
            "priority": priority,
            "class_name": tag_class_for_text(text),
        })

    candidates.sort(key=lambda item: item["priority"])

    for item in candidates[:limit]:
        prepared.append({
            "text": item["text"],
            "is_spoiler": False,
            "class_name": item["class_name"],
        })

    hidden_count = max(0, len(candidates) - len(prepared)) + skipped_count

    return prepared, hidden_count


def prepare_novel_for_template(novel: dict):
    tags = clean_value(novel.get("tags"))
    title = clean_value(novel.get("title"))
    post_icons = clean_value(novel.get("post_icons"))

    relation_type = clean_value(novel.get("relation_type")) or relation_type_from_tags(tags)
    relation_icon = clean_value(novel.get("relation_icon")) or relation_icon_from_tags(tags)
    relation_color = clean_value(novel.get("relation_color")) or relation_color_from_type(relation_type)

    stored_progress = normalize_progress_percent(novel.get("progress_percent"))

    translation_meta = translation_meta_from_status(
        clean_value(novel.get("status")),
        clean_value(novel.get("schedule_mode")),
        stored_progress,
    )

    tag_items = prepare_tag_items(tags)
    card_tag_items, card_hidden_tags = prepare_card_tag_items(tags)

    size_meta = size_meta_from_tags(tags)
    access_badge = access_badge_from_model(
        clean_value(novel.get("access_model")),
        clean_value(novel.get("early_access_mode")),
    )

    age_rating = clean_value(novel.get("age_rating")) or age_rating_from_tags(tags)

    if not age_rating and to_bool(novel.get("has_adult_badge")):
        age_rating = "18+"

    if post_icons:
        novel["display_title"] = f"{post_icons} {title}".strip()
    else:
        novel["display_title"] = title

    novel["post_icons"] = post_icons

    novel["relation_type"] = relation_type
    novel["relation_icon"] = relation_icon
    novel["relation_color"] = relation_color

    novel["size_code"] = size_meta["code"]
    novel["size_label"] = size_meta["label"]

    novel["access_badge"] = access_badge
    novel["age_rating"] = age_rating

    novel["translation_status"] = clean_value(novel.get("translation_status")) or translation_meta["value"]
    novel["translation_status_label"] = clean_value(novel.get("translation_status_label")) or translation_meta["label"]
    novel["translation_status_color"] = clean_value(novel.get("translation_status_color")) or translation_meta["color"]
    novel["translation_status_icon"] = translation_status_icon_from_value(novel["translation_status"])

    if novel["translation_status"] == "completed":
        novel["translation_status_label"] = "Завершена"
    elif novel["translation_status"] == "paused":
        novel["translation_status_label"] = "На передержке"
    else:
        novel["translation_status_label"] = "В процессе перевода"

    novel["project_status_icon"] = novel["translation_status_icon"]

    novel["tags_tooltip"] = clean_value(novel.get("tags_tooltip")) or tags
    novel["tags_short"] = clean_value(novel.get("tags_short")) or "; ".join(split_tags(tags)[:10])

    novel["tag_items"] = tag_items
    novel["catalog_tag_items"] = card_tag_items
    novel["card_tag_items"] = card_tag_items
    novel["catalog_hidden_tags"] = card_hidden_tags
    novel["card_hidden_tags"] = card_hidden_tags

    translated = to_float(novel.get("translated_chapters"))
    total = to_float(novel.get("total_chapters"))

    if stored_progress is not None:
        novel["progress_percent"] = stored_progress
    elif translated is not None and total and total > 0:
        novel["progress_percent"] = round(min(100, max(0, translated / total * 100)), 1)
    else:
        novel["progress_percent"] = None

    return novel


def fetch_miniapp_sheet(sheet_name: str, use_cache: bool = False) -> list[dict]:
    validate_env_value("MINIAPP_SHEET_ID", MINIAPP_SHEET_ID)

    cache_key = f"sheet:{sheet_name}"

    if use_cache:
        cached = SHEET_CACHE.get(cache_key)
        if cached and time.time() - cached["created_at"] < SHEET_CACHE_TTL_SECONDS:
            return cached["rows"]

    encoded_sheet_name = quote(sheet_name)

    url = (
        f"https://docs.google.com/spreadsheets/d/{MINIAPP_SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={encoded_sheet_name}"
    )

    response = requests.get(url, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(
            f"Cannot fetch MiniApp sheet '{sheet_name}'. "
            f"HTTP {response.status_code}."
        )

    text = response.content.decode("utf-8-sig")
    text_lower = text.lower()

    if "<html" in text_lower or ("google" in text_lower and "sign in" in text_lower):
        raise RuntimeError(
            f"MiniApp sheet '{sheet_name}' returned an HTML page instead of CSV. "
            f"Most likely the sheet is not public."
        )

    reader = csv.DictReader(StringIO(text))
    rows = list(reader)

    if not reader.fieldnames:
        raise RuntimeError(
            f"MiniApp sheet '{sheet_name}' has no headers or could not be parsed as CSV."
        )

    if use_cache:
        SHEET_CACHE[cache_key] = {
            "created_at": time.time(),
            "rows": rows,
        }

    return rows


def normalize_fox_name(name: str) -> str:
    name = clean_value(name)

    for suffix in (".png", ".webp", ".jpg", ".jpeg"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]

    return name


def get_fox_assets() -> dict:
    fallback = {
        "fox_peek": "",
        "fox_side": "",
        "fox_hearts": "",
        "fox_sitting_front": "",
        "fox_sitting_side": "",
        "fox_sleeping": "",
        "fox_standing_paws": "",
        "fox_standing_paws_up": "",
        "fox_jumping": "",
        "fox_jumping_paws": "",
        "fox_jump_paws_up": "",
        "fox_laying_paws": "",
        "fox_peek_left": "",
        "fox_peek_right": "",
        "fox_pic": "",
        "fox_heart": "",
    }

    try:
        rows = fetch_miniapp_sheet("Fox", use_cache=True)
    except Exception as error:
        print("Fox sheet warning:", error)
        return fallback

    result = fallback.copy()

    for row in rows:
        raw_name = clean_value(row.get("name") or row.get("Name"))
        url = clean_value(row.get("url") or row.get("URL"))

        if not raw_name or not url:
            continue

        normalized_name = normalize_fox_name(raw_name)

        result[raw_name] = url
        result[normalized_name] = url

    if not result.get("fox_side"):
        result["fox_side"] = result.get("fox_side.png", "")

    if not result.get("fox_hearts"):
        result["fox_hearts"] = result.get("fox_heart", "")

    if not result.get("fox_peek"):
        result["fox_peek"] = (
            result.get("fox_peek_left")
            or result.get("fox_peek_right")
            or result.get("fox_pic")
            or ""
        )

    if not result.get("fox_jumping_paws"):
        result["fox_jumping_paws"] = result.get("fox_jump_paws_up", "")

    if not result.get("fox_standing_paws"):
        result["fox_standing_paws"] = result.get("fox_standing_paws_up", "")

    return result


def sync_novels_to_db(db: Client) -> int:
    rows = fetch_miniapp_sheet("Novels")

    payload_by_id = {}
    duplicate_ids = []

    for row in rows:
        novel_id = to_int(row.get("NovelID"))

        if not novel_id:
            continue

        if novel_id in payload_by_id:
            duplicate_ids.append(novel_id)

        tags = clean_value(row.get("Tags"))
        status = clean_value(row.get("Status"))
        schedule_mode = clean_value(row.get("ScheduleMode"))
        progress_percent = normalize_progress_percent(row.get("ProgressPercent"))

        relation_type = clean_value(row.get("RelationType")) or relation_type_from_tags(tags)
        relation_icon = clean_value(row.get("RelationIcon")) or relation_icon_from_tags(tags)
        relation_color = clean_value(row.get("RelationColor")) or relation_color_from_type(relation_type)

        translation_meta = translation_meta_from_status(status, schedule_mode, progress_percent)

        is_visible = to_bool(row.get("IsVisible"))

        payload_by_id[novel_id] = {
            "id": novel_id,
            "slug": clean_value(row.get("Slug")) or f"novel-{novel_id}",
            "title": clean_value(row.get("Title")) or f"Novel {novel_id}",
            "title_en": clean_value(row.get("TitleEN")),
            "post_icons": clean_value(row.get("PostIcons")),
            "cover_url": clean_value(row.get("CoverURL")),
            "description": clean_value(row.get("Description")),
            "tags": tags,
            "tags_short": clean_value(row.get("TagsShort")),
            "tags_tooltip": clean_value(row.get("TagsTooltip")),
            "top_description": clean_value(row.get("TopDescription")),
            "bottom_description": clean_value(row.get("BottomDescription")),
            "original_language": clean_value(row.get("OriginalLanguage")),
            "translation_author": clean_value(row.get("TranslationAuthor")) or "Зефиркины баоцзы",
            "total_chapters": to_int(row.get("TotalChapters")),
            "translated_chapters": to_int(row.get("TranslatedChapters")),
            "progress_percent": progress_percent,
            "status": status,
            "access_model": clean_value(row.get("AccessModel")),
            "schedule_mode": schedule_mode,
            "early_access_mode": clean_value(row.get("EarlyAccessMode")),
            "translation_status": clean_value(row.get("TranslationStatus")) or translation_meta["value"],
            "translation_status_label": clean_value(row.get("TranslationStatusLabel")) or translation_meta["label"],
            "translation_status_color": clean_value(row.get("TranslationStatusColor")) or translation_meta["color"],
            "relation_type": relation_type,
            "relation_icon": relation_icon,
            "relation_color": relation_color,
            "age_rating": clean_value(row.get("AgeRating")) or age_rating_from_tags(tags),
            "has_adult_badge": to_bool(row.get("HasAdultBadge")),
            "sort_order": to_float(row.get("SortOrder")) or novel_id,
            "is_visible": is_visible,
            "is_active": is_visible,
            "added_date": normalize_date(row.get("AddedDate")),
        }

    payload = list(payload_by_id.values())

    if duplicate_ids:
        print(
            "MiniApp sync warning: duplicate NovelID values were found and deduplicated:",
            sorted(set(duplicate_ids)),
        )

    if payload:
        db.table("novels").upsert(payload, on_conflict="id").execute()

    return len(payload)


def make_unique_chapter_code(base_code: str, row_number: int, used_codes: set[str]) -> str:
    base_code = clean_value(base_code)

    if not base_code:
        base_code = f"row-{row_number}"

    code = base_code

    if code not in used_codes:
        used_codes.add(code)
        return code

    code = f"{base_code}-row-{row_number}"

    while code in used_codes:
        row_number += 1
        code = f"{base_code}-row-{row_number}"

    used_codes.add(code)
    return code


def sync_chapters_to_db(db: Client) -> dict:
    rows = fetch_miniapp_sheet("Chapters")

    payload = []
    used_codes = set()
    skipped_rows = []
    duplicate_base_codes = []

    for row_number, row in enumerate(rows, start=2):
        base_chapter_code = clean_value(row.get("ChapterID"))
        novel_id = to_int(row.get("NovelID"))
        chapter_no = parse_chapter_no_number(row.get("ChapterNo"))

        skip_reasons = []

        if not novel_id:
            skip_reasons.append("empty or invalid NovelID")

        if chapter_no is None:
            skip_reasons.append("empty or invalid ChapterNo")

        if skip_reasons:
            skipped_rows.append({
                "row": row_number,
                "reasons": skip_reasons,
                "ChapterID": row.get("ChapterID"),
                "NovelID": row.get("NovelID"),
                "ChapterNo": row.get("ChapterNo"),
                "ChapterTitle": row.get("ChapterTitle"),
            })
            continue

        if not base_chapter_code:
            base_chapter_code = f"{novel_id}-{row.get('ChapterNo')}-{row_number}"

        if base_chapter_code in used_codes:
            duplicate_base_codes.append(base_chapter_code)

        chapter_code = make_unique_chapter_code(base_chapter_code, row_number, used_codes)

        access_level = clean_value(row.get("AccessLevel")) or "hidden"
        is_visible = to_bool(row.get("IsVisible"))

        sort_order = to_float(row.get("SortOrder"))

        if sort_order is None:
            sort_order = chapter_no

        if sort_order is None:
            sort_order = row_number

        telegraph_url = clean_value(row.get("TelegraphURL"))
        telegraph_free_url = clean_value(row.get("TelegraphFreeURL"))
        telegraph_premium_url = clean_value(row.get("TelegraphPremiumURL"))

        payload.append({
            "chapter_code": chapter_code,
            "novel_id": novel_id,
            "chapter_no": chapter_no,
            "title": clean_chapter_title(row.get("ChapterTitle")) or f"Глава {chapter_no:g}",
            "slug": clean_value(row.get("Slug")) or f"chapter-{row_number}",
            "volume": clean_value(row.get("Volume")),
            "volume_no": to_int(row.get("VolumeNo")),
            "volume_title": clean_value(row.get("VolumeTitle")),
            "translation_date": normalize_date(row.get("TranslationDate")),
            "release_date": normalize_date(row.get("ReleaseDate")),
            "free_release_date": normalize_date(row.get("FreeReleaseDate")),
            "premium_release_date": normalize_date(row.get("PremiumReleaseDate")),
            "telegraph_url": telegraph_url,
            "telegraph_free_url": telegraph_free_url,
            "telegraph_premium_url": telegraph_premium_url,
            "telegraph_free_code": clean_value(row.get("TelegraphFreeCode")),
            "telegraph_premium_code": clean_value(row.get("TelegraphPremiumCode")),
            "source_type": clean_value(row.get("SourceType")) or "telegraph",
            "access_level": access_level,
            "is_visible": is_visible,
            "is_active": is_visible,
            "sort_order": sort_order,
        })

    if duplicate_base_codes:
        print(
            "MiniApp sync warning: duplicate ChapterID values were preserved with suffixes:",
            sorted(set(duplicate_base_codes)),
        )

    if skipped_rows:
        print("MiniApp sync warning: skipped chapter rows:", skipped_rows[:20])

    if payload:
        db.table("chapters").upsert(payload, on_conflict="chapter_code").execute()

    return {
        "read_rows": len(rows),
        "prepared_rows": len(payload),
        "skipped_rows": len(skipped_rows),
        "duplicate_base_codes": sorted(set(duplicate_base_codes)),
        "skipped_examples": skipped_rows[:10],
    }


def sync_miniapp_sheets_to_db() -> dict:
    db = get_admin_supabase()

    novels_count = sync_novels_to_db(db)
    chapters_result = sync_chapters_to_db(db)

    return {
        "status": "ok",
        "novels": novels_count,
        "chapters": chapters_result.get("prepared_rows", 0),
        "chapters_debug": chapters_result,
    }


def build_chapter_display_list(chapters: list[dict]) -> tuple[list[dict], int]:
    sorted_chapters = sorted(
        chapters,
        key=lambda chapter: (
            chapter.get("sort_order") is None,
            chapter.get("sort_order") or chapter.get("chapter_no") or 0,
            chapter.get("id") or 0,
        ),
    )

    display_chapters = []

    for chapter in sorted_chapters:
        access_level = chapter.get("access_level")

        if access_level in ("public", "subscriber"):
            display_chapters.append(chapter)

    return display_chapters, 0


def group_chapters_by_volume(chapters: list[dict]) -> list[dict]:
    groups = []
    group_map = {}

    for chapter in chapters:
        volume_title = clean_value(chapter.get("volume"))

        if not volume_title:
            volume_no = chapter.get("volume_no")
            raw_title = clean_value(chapter.get("volume_title"))

            if volume_no and raw_title:
                volume_title = f"{volume_no}. {raw_title}"
            elif raw_title:
                volume_title = raw_title
            elif volume_no:
                volume_title = f"Том {volume_no}"

        if volume_title and volume_title.isdigit():
            volume_title = f"Том {volume_title}"

        if volume_title not in group_map:
            group = {
                "title": volume_title,
                "chapters": [],
            }
            group_map[volume_title] = group
            groups.append(group)

        chapter["title"] = clean_chapter_title(chapter.get("title"))
        group_map[volume_title]["chapters"].append(chapter)

    if len(groups) == 1 and groups[0]["title"] == "":
        groups[0]["title"] = ""

    return groups


def get_first_readable_chapter(chapters: list[dict]):
    if not chapters:
        return None

    return chapters[0]


def get_neighbor_chapters(db: Client, chapter: dict):
    novel_id = chapter.get("novel_id")
    current_sort = chapter.get("sort_order") or chapter.get("chapter_no") or 0

    previous_result = (
        db.table("chapters")
        .select("id, title, access_level, sort_order")
        .eq("novel_id", novel_id)
        .eq("is_visible", True)
        .lt("sort_order", current_sort)
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )

    next_result = (
        db.table("chapters")
        .select("id, title, access_level, sort_order")
        .eq("novel_id", novel_id)
        .eq("is_visible", True)
        .gt("sort_order", current_sort)
        .order("sort_order")
        .limit(1)
        .execute()
    )

    previous_chapter = (previous_result.data or [None])[0]
    next_chapter = (next_result.data or [None])[0]

    if previous_chapter:
        previous_chapter["title"] = clean_chapter_title(previous_chapter.get("title"))

    if next_chapter:
        next_chapter["title"] = clean_chapter_title(next_chapter.get("title"))

    return previous_chapter, next_chapter


def get_chapter_index_info(db: Client, chapter: dict):
    novel_id = chapter.get("novel_id")

    result = (
        db.table("chapters")
        .select("id, chapter_code, chapter_no, sort_order, access_level, is_visible")
        .eq("novel_id", novel_id)
        .eq("is_visible", True)
        .in_("access_level", ["public", "subscriber"])
        .order("sort_order")
        .execute()
    )

    chapters = result.data or []
    unit_keys = []
    current_key = chapter_unit_key(chapter)

    for item in chapters:
        key = chapter_unit_key(item)

        if not key:
            continue

        if key not in unit_keys:
            unit_keys.append(key)

    available_count = len(unit_keys)
    chapter_index = 0

    if current_key in unit_keys:
        chapter_index = unit_keys.index(current_key) + 1

    return chapter_index, available_count


def normalize_external_article_url(url: str) -> str:
    url = clean_value(url)

    if not url:
        raise HTTPException(status_code=404, detail="Chapter URL is empty")

    if url.startswith("/chapter/"):
        raise HTTPException(
            status_code=400,
            detail="Old internal /chapter/... link found instead of external URL",
        )

    if url.startswith("http://"):
        url = "https://" + url.removeprefix("http://")

    if not url.startswith("https://"):
        url = "https://" + url

    parsed = urlparse(url)

    allowed_hosts = {
        "telegra.ph",
        "teletype.in",
    }

    if parsed.netloc not in allowed_hosts:
        raise HTTPException(
            status_code=400,
            detail=f"Only telegra.ph and teletype.in links are allowed. Got: {parsed.netloc}",
        )

    return url


def clean_article_html(article):
    stop_phrases = [
        "тгк зефиркины баоцзы",
        "зефиркины баоцзы",
        "спасибо, что читаете",
        "спасибо что читаете",
        "полный перевод",
        "доступен на бусти",
        "доступен на boosty",
        "boosty",
        "бусти",
        "bllate",
        "bl late",
        "bl-late",
    ]

    content_tags = article.find_all(["p", "div", "blockquote", "h3", "h4", "a"])

    for tag in content_tags:
        text = tag.get_text(" ", strip=True).lower()

        if any(phrase in text for phrase in stop_phrases):
            current = tag

            while current:
                next_tag = current.find_next_sibling()
                current.decompose()
                current = next_tag

            break

    return article


def fetch_external_article(url: str) -> dict:
    url = normalize_external_article_url(url)

    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 ZefirkiReader/1.0",
        },
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"External article returned HTTP {response.status_code}",
        )

    soup = BeautifulSoup(response.text, "html.parser")
    article = soup.find("article") or soup.find("main")

    if not article:
        article = soup.find("body")

    if not article:
        raise HTTPException(status_code=502, detail="Article content not found")

    for tag in article.select("address, aside, script, style, header, footer, nav"):
        tag.decompose()

    first_h1 = article.find("h1")
    if first_h1:
        first_h1.decompose()

    first_h2 = article.find("h2")
    if first_h2:
        first_h2.decompose()

    article = clean_article_html(article)

    return {
        "source_url": url,
        "content_html": str(article),
    }


@app.get("/", response_class=HTMLResponse)
async def home():
    return RedirectResponse(url="/library", status_code=302)


@app.head("/")
async def home_head():
    return Response(status_code=200)


@app.get("/catalog", response_class=HTMLResponse)
async def old_catalog_redirect():
    return RedirectResponse(url="/library", status_code=302)


@app.get("/library", response_class=HTMLResponse)
async def library(request: Request):
    try:
        db = get_supabase()
        fox = get_fox_assets()

        result = (
            db.table("novels")
            .select("*")
            .eq("is_visible", True)
            .order("sort_order")
            .execute()
        )

        novels = result.data or []

        chapter_count_result = (
            db.table("chapters")
            .select("novel_id, id, chapter_code, chapter_no, access_level, is_visible, sort_order")
            .order("novel_id")
            .order("sort_order")
            .execute()
        )

        chapters_by_novel = {}

        for row in chapter_count_result.data or []:
            novel_id = row.get("novel_id")

            if novel_id not in chapters_by_novel:
                chapters_by_novel[novel_id] = []

            chapters_by_novel[novel_id].append(row)

        for novel in novels:
            prepare_novel_for_template(novel)

            all_chapters = chapters_by_novel.get(novel.get("id"), [])

            display_chapters_count = count_chapter_units_for_card(all_chapters)
            available_chapters_count = count_available_chapter_units(all_chapters)

            novel["display_chapters_count"] = display_chapters_count or novel.get("total_chapters") or 0
            novel["available_chapters_count"] = available_chapters_count

        return templates.TemplateResponse(
            request,
            "library.html",
            {
                "app_title": "Зефиркины баоцзы",
                "novels": novels,
                "fox": fox,
            },
        )

    except Exception as error:
        return make_error_response(error)


@app.get("/novel/{slug}", response_class=HTMLResponse)
async def novel_page(request: Request, slug: str):
    try:
        db = get_supabase()
        fox = get_fox_assets()

        novel_result = (
            db.table("novels")
            .select("*")
            .eq("slug", slug)
            .eq("is_visible", True)
            .limit(1)
            .execute()
        )

        novels = novel_result.data or []

        if not novels:
            raise HTTPException(status_code=404, detail="Novel not found")

        novel = prepare_novel_for_template(novels[0])

        chapters_result = (
            db.table("chapters")
            .select("*")
            .eq("novel_id", novel["id"])
            .order("sort_order")
            .execute()
        )

        all_chapters = chapters_result.data or []

        display_chapters, hidden_subscriber_count = build_chapter_display_list(
            [chapter for chapter in all_chapters if chapter.get("is_visible") is True]
        )

        grouped_chapters = group_chapters_by_volume(display_chapters)
        first_chapter = get_first_readable_chapter(display_chapters)

        novel["display_chapters_count"] = count_chapter_units_for_card(all_chapters) or novel.get("total_chapters") or 0
        novel["available_chapters_count"] = count_available_chapter_units(display_chapters)

        return templates.TemplateResponse(
            request,
            "novel.html",
            {
                "app_title": "Зефиркины баоцзы",
                "novel": novel,
                "chapters": display_chapters,
                "grouped_chapters": grouped_chapters,
                "hidden_subscriber_count": hidden_subscriber_count,
                "first_chapter": first_chapter,
                "fox": fox,
            },
        )

    except HTTPException:
        raise
    except Exception as error:
        return make_error_response(error)


@app.get("/chapter/{chapter_id}", response_class=HTMLResponse)
async def chapter_page(request: Request, chapter_id: int):
    try:
        db = get_supabase()
        fox = get_fox_assets()

        chapter_result = (
            db.table("chapters")
            .select("*, novels(id, title, slug, post_icons)")
            .eq("id", chapter_id)
            .eq("is_visible", True)
            .limit(1)
            .execute()
        )

        chapters = chapter_result.data or []

        if not chapters:
            raise HTTPException(status_code=404, detail="Chapter not found")

        chapter = chapters[0]
        chapter["title"] = clean_chapter_title(chapter.get("title"))

        novel = chapter.get("novels") or {}
        title = clean_value(novel.get("title"))
        post_icons = clean_value(novel.get("post_icons"))

        novel["display_title"] = f"{post_icons} {title}".strip() if post_icons else title

        is_locked = chapter.get("access_level") == "subscriber"
        unlock_date = format_date_ru(
            chapter.get("release_date") or chapter.get("free_release_date")
        )

        previous_chapter, next_chapter = get_neighbor_chapters(db, chapter)
        chapter_index, available_chapters_count = get_chapter_index_info(db, chapter)

        article_url = (
            chapter.get("telegraph_url")
            or chapter.get("telegraph_free_url")
            or chapter.get("telegraph_premium_url")
            or ""
        )

        article_content = None
        article_error = None

        if article_url:
            try:
                article_content = fetch_external_article(article_url)
            except HTTPException as error:
                article_error = error.detail
            except Exception as error:
                article_error = str(error)

        return templates.TemplateResponse(
            request,
            "chapter.html",
            {
                "app_title": "Зефиркины баоцзы",
                "chapter": chapter,
                "chapter_index": chapter_index,
                "available_chapters_count": available_chapters_count,
                "novel": novel,
                "article_content": article_content,
                "article_error": article_error,
                "is_locked": is_locked,
                "unlock_date": unlock_date,
                "previous_chapter": previous_chapter,
                "next_chapter": next_chapter,
                "fox": fox,
            },
        )

    except HTTPException:
        raise
    except Exception as error:
        return make_error_response(error)


@app.post("/admin/sync-from-sheets")
async def admin_sync_from_sheets(request: Request):
    try:
        validate_env_value("SYNC_TOKEN", SYNC_TOKEN)

        token = request.headers.get("X-Sync-Token")

        if token != SYNC_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid sync token")

        return sync_miniapp_sheets_to_db()

    except HTTPException:
        raise
    except Exception as error:
        return make_error_response(error)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.head("/health")
async def health_head():
    return Response(status_code=200)


@app.get("/debug/env")
async def debug_env():
    return {
        "SUPABASE_URL": mask_env_value(SUPABASE_URL),
        "SUPABASE_KEY": mask_env_value(SUPABASE_KEY),
        "SUPABASE_SERVICE_KEY": mask_env_value(SUPABASE_SERVICE_KEY),
        "MINIAPP_SHEET_ID": mask_env_value(MINIAPP_SHEET_ID),
        "SYNC_TOKEN": mask_env_value(SYNC_TOKEN),
    }


@app.get("/debug/supabase")
async def debug_supabase():
    try:
        validate_required_env_for_admin_sync()

        db = get_admin_supabase()

        result = (
            db.table("novels")
            .select("id,title,post_icons,slug")
            .limit(1)
            .execute()
        )

        return {
            "status": "ok",
            "message": "Supabase admin connection works",
            "sample": result.data,
        }

    except Exception as error:
        return make_error_response(error)


@app.get("/debug/library-data")
async def debug_library_data():
    try:
        db = get_supabase()

        novels_result = (
            db.table("novels")
            .select(
                "id,title,post_icons,slug,is_visible,sort_order,"
                "translation_status,translation_status_label,total_chapters,"
                "translated_chapters,progress_percent,tags,age_rating,"
                "access_model,schedule_mode,early_access_mode,relation_type,relation_icon"
            )
            .eq("is_visible", True)
            .order("sort_order")
            .execute()
        )

        chapters_result = (
            db.table("chapters")
            .select(
                "id,chapter_code,novel_id,chapter_no,title,"
                "access_level,is_visible,telegraph_url,"
                "telegraph_free_url,telegraph_premium_url,sort_order"
            )
            .order("novel_id")
            .order("sort_order")
            .limit(1000)
            .execute()
        )

        chapters_by_novel = {}

        for chapter in chapters_result.data or []:
            novel_id = chapter.get("novel_id")

            if novel_id not in chapters_by_novel:
                chapters_by_novel[novel_id] = []

            chapters_by_novel[novel_id].append(chapter)

        novels_sample = []

        for novel in novels_result.data or []:
            prepared = prepare_novel_for_template(dict(novel))
            all_chapters = chapters_by_novel.get(novel.get("id"), [])

            prepared["display_chapters_count"] = count_chapter_units_for_card(all_chapters)
            prepared["available_chapters_count"] = count_available_chapter_units(all_chapters)
            prepared["normalized_progress_percent"] = normalize_progress_percent(
                novel.get("progress_percent")
            )

            novels_sample.append(prepared)

        return {
            "status": "ok",
            "novels_count": len(novels_result.data or []),
            "chapters_count_sample": len(chapters_result.data or []),
            "novels_sample": novels_sample[:30],
            "chapters_sample": chapters_result.data[:100] if chapters_result.data else [],
        }

    except Exception as error:
        return make_error_response(error)


@app.get("/debug/fox")
async def debug_fox():
    try:
        fox = get_fox_assets()

        return {
            "status": "ok",
            "fox": fox,
        }

    except Exception as error:
        return make_error_response(error)
