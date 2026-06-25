import os
import re
import html
import json
import hmac
import time
import base64
import hashlib
import traceback
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin, urlparse, parse_qsl

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from bs4 import BeautifulSoup

load_dotenv()

APP_TITLE = "Зефиркины баоцзы"
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or ""
SYNC_TOKEN = os.getenv("SYNC_TOKEN") or ""

# Telegram Mini App authentication and membership-based access.
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
def normalize_telegram_chat_id(value: Any) -> str:
    """Normalize chat IDs copied from Telegram tools or spreadsheets.

    Accepts full IDs such as -1003825580200 and positive values such as
    3825580200 (the common representation without the -100 prefix).
    Spaces, non-breaking spaces and separators are ignored.
    """
    text = str(value or "")
    text = re.sub(r"[\s\u00a0_,]", "", text)
    if not text:
        return ""
    if text.startswith("-100") and text[4:].isdigit():
        return text
    if text.startswith("-") and text[1:].isdigit():
        return text
    if text.isdigit():
        return f"-100{text}"
    return text


TRAVELER_CHAT_ID = normalize_telegram_chat_id(os.getenv("TRAVELER_CHAT_ID"))
KEEPER_CHAT_ID = normalize_telegram_chat_id(os.getenv("KEEPER_CHAT_ID"))
SESSION_SECRET = (os.getenv("SESSION_SECRET") or TELEGRAM_BOT_TOKEN or SYNC_TOKEN or "change-me").encode("utf-8")
AUTH_COOKIE_NAME = "zefirki_access"
AUTH_SESSION_TTL_SECONDS = int(os.getenv("AUTH_SESSION_TTL_SECONDS") or "900")
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = int(os.getenv("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS") or "86400")
MEMBERSHIP_CACHE_SECONDS = int(os.getenv("MEMBERSHIP_CACHE_SECONDS") or "300")
APP_ENV = (os.getenv("APP_ENV") or "production").lower()

# Tribute subscriptions and book-specific purchases.
TRIBUTE_API_KEY = (os.getenv("TRIBUTE_API_KEY") or "").strip()
TRIBUTE_TRAVELER_SUBSCRIPTION_ID = (os.getenv("TRIBUTE_TRAVELER_SUBSCRIPTION_ID") or "").strip()
TRIBUTE_KEEPER_SUBSCRIPTION_ID = (os.getenv("TRIBUTE_KEEPER_SUBSCRIPTION_ID") or "").strip()
TRIBUTE_TRAVELER_URL = (os.getenv("TRIBUTE_TRAVELER_URL") or "").strip()
TRIBUTE_KEEPER_URL = (os.getenv("TRIBUTE_KEEPER_URL") or "").strip()
ACCESS_DEBUG_ENABLED = (os.getenv("ACCESS_DEBUG_ENABLED") or "true").lower() in {"1", "true", "yes", "on"}

ROLE_RANK = {"guest": 0, "traveler": 1, "keeper": 2}
_membership_cache: dict[int, tuple[float, dict[str, Any]]] = {}

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

app = FastAPI(title="Zefirki Reader Mini App")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def role_rank(role: Any) -> int:
    return ROLE_RANK.get(str(role or "guest").lower(), 0)


def public_viewer(viewer: dict[str, Any]) -> dict[str, Any]:
    role = str(viewer.get("role") or "guest")
    return {
        "authenticated": bool(viewer.get("authenticated")),
        "user_id": viewer.get("user_id"),
        "first_name": viewer.get("first_name") or "",
        "username": viewer.get("username") or "",
        # Роль остаётся только техническим признаком для проверки доступа.
        # В интерфейсе она не выводится.
        "role": role,
    }


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def make_session_token(viewer: dict[str, Any]) -> str:
    payload = {
        "user_id": int(viewer["user_id"]),
        "first_name": str(viewer.get("first_name") or "")[:120],
        "username": str(viewer.get("username") or "")[:120],
        "role": str(viewer.get("role") or "guest"),
        "exp": int(time.time()) + AUTH_SESSION_TTL_SECONDS,
    }
    body = b64url_encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signature = b64url_encode(hmac.new(SESSION_SECRET, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def parse_session_token(token: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    body, signature = token.split(".", 1)
    expected = b64url_encode(hmac.new(SESSION_SECRET, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(b64url_decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    role = str(payload.get("role") or "guest")
    if role not in ROLE_RANK:
        return None
    return {
        "authenticated": True,
        "user_id": int(payload.get("user_id")),
        "first_name": str(payload.get("first_name") or ""),
        "username": str(payload.get("username") or ""),
        "role": role,
    }


def viewer_from_request(request: Request) -> dict[str, Any]:
    session = parse_session_token(request.cookies.get(AUTH_COOKIE_NAME, ""))
    if session:
        return session
    return {
        "authenticated": False,
        "user_id": None,
        "first_name": "",
        "username": "",
        "role": "guest",
    }


def validate_telegram_init_data(init_data: str) -> dict[str, Any]:
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN не настроен")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Некорректные данные Telegram") from exc

    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="Telegram hash отсутствует")

    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", TELEGRAM_BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_hash, calculated_hash):
        raise HTTPException(status_code=401, detail="Подпись Telegram не прошла проверку")

    auth_date = int(pairs.get("auth_date") or 0)
    now = int(time.time())
    if not auth_date or auth_date > now + 60 or now - auth_date > TELEGRAM_INIT_DATA_MAX_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="Данные Telegram устарели")

    try:
        user = json.loads(pairs.get("user") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=401, detail="Пользователь Telegram не найден") from exc
    if not user.get("id"):
        raise HTTPException(status_code=401, detail="ID пользователя Telegram отсутствует")
    return user


def telegram_member_is_active(result: dict[str, Any]) -> bool:
    status = str(result.get("status") or "")
    if status in {"creator", "administrator", "member"}:
        return True
    if status == "restricted":
        return bool(result.get("is_member"))
    return False


def check_telegram_membership(chat_id: str, user_id: int) -> bool:
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChatMember",
            params={"chat_id": chat_id, "user_id": user_id},
            timeout=12,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as error:
        print("Telegram membership check failed:", error)
        return False
    if not data.get("ok"):
        print("Telegram getChatMember error:", data.get("description"))
        return False
    return telegram_member_is_active(data.get("result") or {})


def resolve_telegram_role(user_id: int, force_refresh: bool = False) -> str:
    cached = _membership_cache.get(user_id)
    now = time.time()
    if not force_refresh and cached and cached[0] > now:
        return str(cached[1].get("role") or "guest")

    # Keeper wins if the user belongs to both groups.
    if check_telegram_membership(KEEPER_CHAT_ID, user_id):
        role = "keeper"
    elif check_telegram_membership(TRAVELER_CHAT_ID, user_id):
        role = "traveler"
    else:
        role = "guest"
    _membership_cache[user_id] = (now + MEMBERSHIP_CACHE_SECONDS, {"role": role})
    return role


def authenticate_telegram_viewer(init_data: str, force_refresh: bool = True) -> dict[str, Any]:
    user = validate_telegram_init_data(init_data)
    user_id = int(user["id"])
    role = resolve_telegram_role(user_id, force_refresh=force_refresh)
    return {
        "authenticated": True,
        "user_id": user_id,
        "first_name": str(user.get("first_name") or ""),
        "username": str(user.get("username") or ""),
        "role": role,
    }


def novel_required_role(novel: dict) -> str:
    text = f"{novel.get('access_model', '')} {novel.get('early_access_mode', '')}".lower()
    if any(marker in text for marker in ("keeper", "хранитель", "📜")):
        return "keeper"
    if any(marker in text for marker in ("boostyonly", "boosty only", "boosty", "🎁")):
        return "traveler"
    return "guest"


def normalize_required_role(access_level: Any) -> str:
    text = clean_value(access_level).lower()
    if text in {"", "public", "free", "open", "guest"}:
        return "guest"
    if text in {"subscriber", "subscription", "boosty", "traveler", "reader", "stranger"}:
        return "traveler"
    if text in {"premium", "paid", "early", "keeper", "guardian", "all", "hidden"}:
        return "keeper"
    if any(marker in text for marker in ("boosty", "подпис", "странств")):
        return "traveler"
    return "keeper"


def viewer_can_access_required_role(viewer_role: str, required_role: str) -> bool:
    return role_rank(viewer_role) >= role_rank(required_role)


def chapter_public_url(chapter: dict) -> str:
    required = normalize_required_role(chapter.get("access_level"))
    free_url = clean_value(chapter.get("telegraph_free_url"))
    if free_url:
        return free_url
    if required == "guest":
        return clean_value(chapter.get("telegraph_url"))
    return ""


def chapter_premium_url(chapter: dict) -> str:
    """Return only the dedicated premium chapter source.

    A free/public URL must never be used as a premium fallback: otherwise a
    PremiumReleaseDate could accidentally expose the public copy before its
    FreeReleaseDate. Full-book access may still fall back to the free source in
    chapter_content_url_for_access(), where that behaviour is explicit.
    """
    return clean_value(chapter.get("telegraph_premium_url"))


def chapter_public_ready(chapter: dict) -> bool:
    """Fail-closed check for an ordinary free release.

    A chapter is free only when all three conditions are true:
    1. the chapter is translated;
    2. FreeReleaseDate is explicitly present and has arrived;
    3. a free Telegraph URL/code is available.

    Missing FreeReleaseDate must never mean "already free".
    """
    if not chapter_is_translated(chapter):
        return False

    release = clean_value(chapter.get("free_release_date"))
    if not release or not is_date_open(release):
        return False

    return bool(chapter_public_url(chapter))


def chapter_premium_ready(chapter: dict) -> bool:
    """Fail-closed check for a Keeper scheduled release.

    Missing PremiumReleaseDate must never grant access. A Keeper receives the
    chapter only after the explicit premium date and only when premium content
    exists.
    """
    if not chapter_is_translated(chapter):
        return False

    release = clean_value(chapter.get("premium_release_date"))
    if not release or not is_date_open(release):
        return False

    return bool(chapter_premium_url(chapter))


def chapter_content_url_for_role(chapter: dict, viewer_role: str) -> str:
    """Legacy helper kept for older code paths.

    Traveler never has a chapter-level release. It can only see gift novels.
    Keeper receives premium releases; every role receives free releases.
    """
    if chapter.get("is_visible") is not True:
        return ""
    if viewer_role == "keeper" and chapter_premium_ready(chapter):
        return chapter_premium_url(chapter)
    if chapter_public_ready(chapter):
        return chapter_public_url(chapter)
    return ""


def chapter_preview_url(chapter: dict) -> str:
    """Return a source only for a translated, scheduled locked chapter.

    The route that uses this helper must still return only the short server-side
    preview, never the source URL or the full chapter body.
    """
    if chapter.get("is_visible") is not True:
        return ""
    if not chapter_is_translated(chapter):
        return ""

    premium_release = clean_value(chapter.get("premium_release_date"))
    free_release = clean_value(chapter.get("free_release_date"))

    # A chapter with no release dates is an unscheduled/internal row and must not
    # be exposed in MiniApp, even as a paid-release preview.
    if not premium_release and not free_release:
        return ""

    return chapter_premium_url(chapter) or chapter_public_url(chapter)


def access_copy(required_role: str) -> dict[str, str]:
    if required_role == "keeper":
        return {
            "title": "Продолжение доступно Хранителю свитков",
            "description": "Хранитель свитков открывает все главы и все новеллы читалки",
        }
    return {
        "title": "Глава пока закрыта",
        "description": "Она откроется бесплатно по расписанию. Ранний релиз доступен 📜 Хранителю свитков; полный доступ к этой новелле также может быть выдан отдельной покупкой",
    }

def clean_value(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    if value.lower() in ("nan", "none", "null", "undefined"):
        return ""
    return value


def normalize_slug(value: Any) -> str:
    value = clean_value(value).lower().replace("ё", "е")
    value = re.sub(r"[^\wа-яА-Я-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "item"


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


def normalize_progress_percent(value: Any) -> float | int:
    progress = to_float(value, 0.0)
    while progress > 100:
        progress = progress / 100
    progress = max(0, min(100, progress))
    return int(progress) if progress.is_integer() else round(progress, 1)


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def parse_date(value: Any) -> str | None:
    """Normalize a spreadsheet date for PostgreSQL/Supabase DATE columns.

    Supabase/PostgreSQL DATE columns must receive either an ISO date string or
    JSON null. Google Sheets formulas can leak several visually-empty values:
    empty string, ``""``, ``\"\"`` and even strings wrapped in repeated quotes.
    All of them are converted to None here before the row is sent to Supabase.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    text = str(value).strip()

    if not text:
        return None

    # Normalise escaped quote markers that can arrive from Apps Script/JSON:
    #   \"\"  -> ""
    #   \'\'  -> ''
    # Do this before stripping paired outer quotes.
    text = text.replace('\\"', '"').replace("\\'", "'").strip()

    # Unwrap paired outer quotes several times:
    #   '""'      -> empty
    #   '""'  -> empty after the replacement above
    for _ in range(5):
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
            text = text[1:-1].strip()
        else:
            break

    if not text:
        return None

    if text.lower() in {
        'null', 'none', 'undefined', 'nan', 'nat', 'n/a', 'na', '-', '—', '""', "''",
    }:
        return None

    # Accept ISO dates and ISO datetimes generated by Apps Script.
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[T\s].*)?$", text)
    if iso_match:
        candidate = iso_match.group(1)
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None

    for fmt in (
        "%d.%m.%Y", "%d/%m/%Y", "%Y.%m.%d", "%Y/%m/%d",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    # An unrecognized value must not be passed to a DATE column.
    return None


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
    return [clean_value(part) for part in re.split(r"[;,\n]+", text) if clean_value(part)]


def strip_leading_service_icons_from_title(title: Any) -> str:
    title_text = clean_value(title)
    return re.sub(r"^[\s💙❤️💚✅🛠⏳🟢🟡🔴🎁📗📖]+", "", title_text).strip()


def compact_title_with_icons(post_icons: Any, title: Any) -> str:
    title_text = clean_value(title)
    icons = clean_value(post_icons)
    if not title_text:
        return ""
    clean_title = strip_leading_service_icons_from_title(title_text) or title_text
    return f"{icons} {clean_title}".strip() if icons else clean_title


def supabase_ready() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_headers(prefer: str | None = None, range_header: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    if range_header:
        headers["Range-Unit"] = "items"
        headers["Range"] = range_header
    return headers


def supabase_request(
    method: str,
    table: str,
    params: dict[str, Any] | None = None,
    payload: Any | None = None,
    prefer: str | None = None,
    range_header: str | None = None,
) -> Any:
    if not supabase_ready():
        raise RuntimeError("Supabase env vars are not configured")
    response = requests.request(
        method=method,
        url=f"{SUPABASE_URL}/rest/v1/{table}",
        headers=supabase_headers(prefer=prefer, range_header=range_header),
        params=params or {},
        json=payload,
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase error {response.status_code}: {response.text}")
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
    params: dict[str, Any] = {"select": select}
    if filters:
        params.update(filters)
    if order:
        params["order"] = order
    if limit:
        params["limit"] = limit
        result = supabase_request("GET", table, params=params)
        return result if isinstance(result, list) else []

    # Supabase часто отдаёт 1000 строк по умолчанию. Поэтому читаем постранично.
    all_rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        result = supabase_request("GET", table, params=params, range_header=f"{offset}-{offset + page_size - 1}")
        if not isinstance(result, list) or not result:
            break
        all_rows.extend(result)
        if len(result) < page_size:
            break
        offset += page_size
    return all_rows


def db_upsert(
    table: str,
    rows: list[dict],
    conflict_key: str,
    batch_size: int = 100,
) -> int:
    """Upsert rows to Supabase in bounded batches.

    Returning full representations for hundreds of chapter rows made the sync
    unnecessarily heavy and could time out on Render/Supabase. We ask PostgREST
    for a minimal response and count successfully submitted rows ourselves.
    """
    if not rows:
        return 0

    safe_batch_size = max(1, min(int(batch_size or 100), 250))
    submitted = 0

    for start in range(0, len(rows), safe_batch_size):
        batch = rows[start:start + safe_batch_size]
        batch_number = start // safe_batch_size + 1
        try:
            supabase_request(
                "POST",
                table,
                params={"on_conflict": conflict_key},
                payload=batch,
                prefer="resolution=merge-duplicates,return=minimal",
            )
        except Exception as error:
            raise RuntimeError(
                f"Ошибка Supabase: таблица {table}, пакет {batch_number}, "
                f"строки {start + 1}-{start + len(batch)}. {error}"
            ) from error
        submitted += len(batch)

    return submitted


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
        if shown_text:
            result.append({"text": shown_text, "raw_text": text, "is_spoiler": is_spoiler, "class_name": tag_class_name(shown_text)})
    return result


def normalize_tag_text_for_priority(tag: Any) -> str:
    return clean_value(tag).replace("!", "").strip().lower()


def is_age_rating_tag(tag: Any) -> bool:
    return normalize_tag_text_for_priority(tag) in ("g", "pg", "pg-13", "r", "r18", "r-18", "nc-17", "16+", "18+", "21+")


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
        "s", "m", "l", "мини", "миди", "макси", "💙", "❤️", "💚", "✅", "🛠", "⏳",
        "🟢", "🟡", "🔴", "🎁", "📗", "📖", "завершена", "завершено",
        "в процессе перевода", "переводится", "на передержке", "скоро", "часть платно",
        "частично платно", "платно", "boosty only",
        "ch", "cn", "zh", "ru", "en",
    }
    return normalized in hidden_tags


def tag_priority_score(tag: dict) -> int:
    text = normalize_tag_text_for_priority(tag.get("text"))
    if tag.get("is_spoiler"):
        return 999
    if is_age_rating_tag(text):
        return 998
    if text in {"гет", "слэш", "bl", "бл", "данмэй", "джен", "нет любовной линии"}:
        return 1
    if text in {"китай", "корея", "япония", "англия", "сша"}:
        return 2
    if text in {"pov героини", "pov героя", "pov пассива", "pov актива"}:
        return 3
    if text in {"сянься/уся", "уся/сянься", "фэнтези", "романтика", "приключения", "юмор", "детектив", "мистика/оккультизм", "магия", "звери", "зверолюди/оборотни", "реинкарнация/возрождение", "здоровые отношения"}:
        return 4
    return 50


def build_card_tag_items(tag_items: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for item in tag_items:
        text = clean_value(item.get("text"))
        normalized = normalize_tag_text_for_priority(text)
        if not text or item.get("is_spoiler") or is_age_rating_tag(text) or is_card_hidden_tag(text) or normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
    return sorted(result, key=lambda item: (tag_priority_score(item), clean_value(item.get("text")).lower()))


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
    return {"completed": "Завершено", "paused": "На паузе", "soon": "Скоро", "in_progress": "Переводится"}.get(status, "Переводится")


def translation_status_color(status: str, fallback: Any = "") -> str:
    fallback_text = clean_value(fallback)
    if fallback_text:
        return fallback_text
    return {"completed": "#44bb44", "paused": "#f59e0b", "soon": "#4f7cff", "in_progress": "#7c5cff"}.get(status, "#7c5cff")


def build_access_badge(access_model: Any, early_access_mode: Any = "") -> dict | None:
    text = f"{clean_value(access_model)} {clean_value(early_access_mode)}".lower()
    if not text.strip():
        return None
    if "boosty" in text or "boostyonly" in text or "🎁" in text:
        return {"icon": "🎁", "label": "Boosty only", "class_name": "access-boosty"}
    if "mini" in text or "🧲" in text:
        return {"icon": "🔴", "label": "Платно", "class_name": "access-paid"}
    if "auto" in text or "early" in text or "⏰" in text:
        return {"icon": "🟡", "label": "Часть платно", "class_name": "access-partial"}
    if "core" in text or "🌷" in text:
        return {"icon": "🟢", "label": "Через 🌱", "class_name": "access-core"}
    return {"icon": "🟡", "label": "Часть платно", "class_name": "access-partial"}


def parse_chapter_no_number(value: Any) -> float:
    text = clean_value(value).replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def normalize_chapter_no_for_unit(value: Any) -> str:
    text = clean_value(value).replace(",", ".").strip()
    if not text:
        return ""
    lowered = text.lower()
    for pattern in (r"^(\d+)[-–—_]\d+$", r"^(\d+)\.\d+$", r"^(\d+)\s*(?:часть|ч\.|part)\s*\d+$", r"^глава\s*(\d+)"):
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    match = re.search(r"\d+", text)
    return match.group(0) if match else text.lower()


def display_number(value: Any) -> str:
    """Preserve an original chapter number as readable text without .0 noise."""
    text = clean_value(value).replace(",", ".")
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def chapter_source_label(chapter: dict) -> str:
    source_no = display_number(chapter.get("source_chapter_no")) or display_number(chapter.get("chapter_no"))
    part_no = display_number(chapter.get("part_no"))
    label = f"Глава {source_no}" if source_no else "Глава"
    if part_no:
        label += f". Часть {part_no}"
    return label


def chapter_meaningful_title(chapter: dict) -> str:
    """Remove an old generic chapter prefix so the new original numbering is not duplicated."""
    title = clean_value(chapter.get("chapter_title") or chapter.get("title"))
    if not title:
        return ""
    cleaned = re.sub(
        r"^\s*глава\s*[\d.,-]+(?:\s*[.:-]\s*|\s+)",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(
        r"^\s*часть\s*\d+\s*[.:-]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    # Generic titles such as “Глава 12” contain no useful subtitle.
    if re.fullmatch(r"глава\s*[\d.,-]+", title, flags=re.IGNORECASE):
        return ""
    return cleaned or ""


def chapter_display_title(chapter: dict) -> str:
    label = chapter_source_label(chapter)
    subtitle = chapter_meaningful_title(chapter)
    return f"{label} — {subtitle}" if subtitle else label


def chapter_code_value(chapter: dict) -> str:
    return clean_value(chapter.get("chapter_code")) or clean_value(chapter.get("chapter_id"))


def chapter_unit_key(chapter: dict) -> str:
    # Every ChapterNo is a separate MiniApp reading unit, including parts.
    return chapter_code_value(chapter) or f"{clean_value(chapter.get('novel_id'))}:{clean_value(chapter.get('chapter_no'))}"



def chapter_has_readable_url(chapter: dict) -> bool:
    return bool(clean_value(chapter.get("telegraph_url")) or clean_value(chapter.get("telegraph_free_url")) or clean_value(chapter.get("telegraph_premium_url")))


def chapter_is_available(chapter: dict, viewer_role: str = "guest") -> bool:
    return bool(chapter_content_url_for_role(chapter, viewer_role))


def count_chapter_units_for_card(chapters: list[dict]) -> int:
    return len({chapter_unit_key(chapter) for chapter in chapters})


def count_available_chapter_units(chapters: list[dict], viewer_role: str = "guest") -> int:
    return len({chapter_unit_key(chapter) for chapter in chapters if chapter_is_available(chapter, viewer_role)})


def choose_chapter_url(chapter: dict, viewer_role: str = "guest") -> str:
    return chapter_content_url_for_role(chapter, viewer_role)


def prepare_chapter_for_template(chapter: dict, viewer_role: str = "guest") -> dict:
    prepared = dict(chapter)
    chapter_code = chapter_code_value(chapter)
    required_role = normalize_required_role(chapter.get("access_level"))
    prepared["id"] = chapter_code
    prepared["chapter_id"] = chapter_code
    prepared["chapter_code"] = chapter_code
    prepared["chapter_no"] = clean_value(chapter.get("chapter_no"))
    prepared["source_chapter_no"] = clean_value(chapter.get("source_chapter_no")) or prepared["chapter_no"]
    prepared["part_no"] = clean_value(chapter.get("part_no"))
    prepared["source_label"] = chapter_source_label(chapter)
    prepared["title"] = chapter_display_title(chapter)
    prepared["display_title"] = prepared["title"]
    prepared["required_role"] = required_role
    prepared["url"] = choose_chapter_url(chapter, viewer_role)
    prepared["is_available"] = bool(prepared["url"])
    prepared["viewer_role"] = viewer_role

    if prepared["is_available"]:
        # Не показываем пользователю, через какой именно уровень доступа
        # открылась глава. В интерфейсе достаточно нейтрального статуса.
        prepared["access_label"] = "Открыта"
        prepared["access_class"] = "chapter-access-public"
    elif required_role == "keeper":
        prepared["access_label"] = "📜 Хранитель свитков"
        prepared["access_class"] = "chapter-access-keeper"
    else:
        prepared["access_label"] = "⏳ Скоро откроется"
        prepared["access_class"] = "chapter-access-hidden"

    prepared["sort_value"] = to_float(chapter.get("sort_order"), parse_chapter_no_number(chapter.get("chapter_no")))
    return prepared


def sort_chapters(chapters: list[dict]) -> list[dict]:
    return sorted(chapters, key=lambda chapter: (to_float(chapter.get("sort_order"), parse_chapter_no_number(chapter.get("chapter_no"))), parse_chapter_no_number(chapter.get("chapter_no")), chapter_code_value(chapter)))


def build_chapter_display_list(chapters: list[dict], viewer_role: str = "guest") -> tuple[list[dict], int]:
    prepared = [
        prepare_chapter_for_template(chapter, viewer_role)
        for chapter in sort_chapters(chapters)
        if viewer_role == "keeper" or chapter.get("is_visible") is True
    ]

    # Показываем не более трёх закрытых глав как понятный предпросмотр.
    # Все доступные текущему пользователю главы остаются видимыми.
    locked_preview_limit = 3
    locked_seen = 0
    hidden_locked_count = 0

    for chapter in prepared:
        chapter["is_paid_extra"] = False
        chapter["hidden"] = False

        if chapter.get("is_available"):
            continue

        locked_seen += 1
        if locked_seen > locked_preview_limit:
            chapter["is_paid_extra"] = True
            chapter["hidden"] = True
            hidden_locked_count += 1

    return prepared, hidden_locked_count


def get_chapter_index_info(chapters: list[dict], current_chapter_id: str, viewer_role: str = "guest") -> dict:
    sorted_visible = [
        prepare_chapter_for_template(chapter, viewer_role)
        for chapter in sort_chapters(chapters)
        if chapter_is_available(chapter, viewer_role)
    ]
    units = []
    seen_units = set()
    for chapter in sorted_visible:
        key = chapter_unit_key(chapter)
        if key not in seen_units:
            seen_units.add(key)
            units.append({"unit_key": key, "chapter_id": chapter.get("chapter_id"), "chapter_title": chapter.get("title")})
    current_index = 0
    for index, unit in enumerate(units, start=1):
        if clean_value(unit.get("chapter_id")) == clean_value(current_chapter_id):
            current_index = index
            break
    return {"chapter_index": current_index, "available_chapters": len(units)}


def get_neighbor_chapters(chapters: list[dict], current_chapter_id: str, viewer_role: str = "guest") -> tuple[dict | None, dict | None]:
    available = [
        prepare_chapter_for_template(chapter, viewer_role)
        for chapter in sort_chapters(chapters)
        if chapter_is_available(chapter, viewer_role)
    ]
    index = next((i for i, chapter in enumerate(available) if clean_value(chapter.get("chapter_id")) == clean_value(current_chapter_id)), None)
    if index is None:
        return None, None
    previous_chapter = available[index - 1] if index > 0 else None
    next_chapter = available[index + 1] if index + 1 < len(available) else None
    return previous_chapter, next_chapter


def split_text_paragraphs(value: Any) -> list[str]:
    """Preserve paragraph breaks from the sheet instead of rendering a wall of text."""
    text = clean_value(value)

    if not text:
        return []

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)

    if "\n\n" in text:
        parts = re.split(r"\n\s*\n", text)
    else:
        parts = text.split("\n")

    paragraphs = []

    for part in parts:
        paragraph = re.sub(r"[ \t]+", " ", clean_value(part))

        if paragraph:
            paragraphs.append(paragraph)

    return paragraphs

def normalize_title_for_compare(value: Any) -> str:
    """Сравнивает названия без регистра, кавычек и декоративной пунктуации."""
    text = clean_value(value).casefold()
    # NovelShort и NovelTitleRu могут отличаться только кавычками, тире или
    # дополнительными пробелами. Для выбора второй строки это одно название.
    text = re.sub(r"[^0-9a-zа-яё]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def prepare_novel_for_template(novel: dict) -> dict:
    prepared = dict(novel)
    title = clean_value(novel.get("title"))
    secondary_title = clean_value(novel.get("title_en"))
    post_icons = clean_value(novel.get("post_icons"))
    tags = clean_value(novel.get("tags"))

    explicit_short_title = clean_value(
        novel.get("short_title")
        or novel.get("title_short")
        or novel.get("novel_short")
        or novel.get("short_name")
    )
    explicit_full_title = clean_value(
        novel.get("full_title")
        or novel.get("title_ru")
        or novel.get("novel_title_ru")
    )

    # В текущей схеме хранения:
    #   title    = NovelShort;
    #   title_en = нужная вторая строка библиотеки:
    #              NovelTitleRu, если оно отличается от короткого,
    #              NovelTitleEn, только если короткое и полное русские совпадают.
    # Поэтому английское название не показывается как обычная дополнительная строка.
    short_title = explicit_short_title or title
    stored_secondary_title = secondary_title
    stored_secondary_is_russian = bool(re.search(r"[А-Яа-яЁё]", stored_secondary_title))

    if explicit_full_title:
        full_title = explicit_full_title
    elif stored_secondary_is_russian:
        full_title = stored_secondary_title
    else:
        full_title = short_title

    english_title = clean_value(
        novel.get("english_title")
        or novel.get("novel_title_en")
        or novel.get("title_en_original")
        or (stored_secondary_title if stored_secondary_title and not stored_secondary_is_russian else "")
    )

    short_equals_full = bool(
        normalize_title_for_compare(short_title)
        and normalize_title_for_compare(short_title) == normalize_title_for_compare(full_title)
    )

    if explicit_full_title:
        library_secondary_title = english_title if short_equals_full else full_title
    else:
        # После синхронизации title_en уже содержит ровно ту вторую строку,
        # которая нужна карточке. Не пытаемся показывать английское название
        # в остальных случаях.
        library_secondary_title = stored_secondary_title

    tag_items = prepare_tag_items(tags)
    card_tag_items = build_card_tag_items(tag_items)
    translation_status = normalize_translation_status(novel.get("translation_status") or novel.get("status"), novel.get("translation_status_label"))
    progress_percent = normalize_progress_percent(novel.get("progress_percent"))
    prepared.update({
        "id": clean_value(novel.get("id")),
        "slug": clean_value(novel.get("slug")) or normalize_slug(title),
        "title": title,
        "display_title": compact_title_with_icons(post_icons, full_title or title),
        # В библиотеке главным становится NovelShort. Второй строкой показываем
        # NovelTitleRu, а при совпадении короткого и полного названий — NovelTitleEn.
        "library_short_title": compact_title_with_icons(post_icons, short_title or title),
        "library_full_title": full_title,
        "library_english_title": english_title,
        "library_secondary_title": library_secondary_title,
        # На странице оглавления английское название выводится только когда оно известно.
        "title_en": english_title,
        "post_icons": post_icons,
        "cover_url": clean_value(novel.get("cover_url")),
        "description": clean_value(novel.get("description")),
        "description_paragraphs": split_text_paragraphs(novel.get("description")),
        "top_description": clean_value(novel.get("top_description")),
        "bottom_description": clean_value(novel.get("bottom_description")),
        "tags": tags,
        "tag_items": tag_items,
        "catalog_tag_items": card_tag_items[:6],
        "card_tag_items": card_tag_items[:6],
        "catalog_hidden_tags": max(0, len(card_tag_items) - 4),
        "age_rating": clean_value(novel.get("age_rating")) or get_age_rating_from_tags(tags),
        "total_chapters": to_int(novel.get("total_chapters"), 0),
        "translated_chapters": to_int(novel.get("translated_chapters"), 0),
        "progress_percent": progress_percent,
        "normalized_progress_percent": progress_percent,
        "translation_status": translation_status,
        "translation_status_label": (
            "Скоро"
            if translation_status == "paused"
            else translation_status_label(translation_status, novel.get("translation_status_label"))
        ),
        "translation_status_color": translation_status_color(translation_status, novel.get("translation_status_color")),
        "access_badge": build_access_badge(novel.get("access_model"), novel.get("early_access_mode")),
        "relation_type": clean_value(novel.get("relation_type")),
        "relation_icon": clean_value(novel.get("relation_icon")),
        "relation_color": clean_value(novel.get("relation_color")),
        "sort_order": to_float(novel.get("sort_order"), 999999),
        "is_visible": to_bool(novel.get("is_visible"), True),
        "added_date": parse_date(novel.get("added_date")),
        "translation_author": clean_value(novel.get("translation_author")),
    })
    prepared["has_adult_badge"] = to_bool(novel.get("has_adult_badge"), False) or prepared["age_rating"] in ("18+", "21+", "NC-17", "R")
    prepared["display_chapters_count"] = to_int(novel.get("display_chapters_count"), prepared["total_chapters"])
    prepared["available_chapters_count"] = to_int(novel.get("available_chapters_count"), 0)
    return prepared


def finalize_novel_access_summary(prepared: dict) -> dict:
    """
    Подготавливает только значимые показатели доступа.

    В MiniApp нет отдельного уровня глав для Странствующего.
    Он видит подарочные новеллы, но читает в них только бесплатные главы.
    Платный/ранний диапазон карточки — это разница между доступом Хранителя
    и бесплатным доступом.
    """
    total = max(0, to_int(prepared.get("display_chapters_count"), 0))
    free_count = max(0, to_int(prepared.get("free_chapters_count"), 0))
    keeper_count = max(0, to_int(prepared.get("keeper_chapters_count"), 0))

    # Backward-compatible field for old templates/data attributes. It must never
    # represent a separate chapter entitlement.
    prepared["traveler_chapters_count"] = free_count

    all_free = total > 0 and free_count >= total
    show_free = free_count > 0
    show_keeper = keeper_count > free_count
    boosty_paid_count = max(0, keeper_count - free_count)

    prepared["all_chapters_free"] = all_free
    prepared["show_free_stat"] = show_free
    prepared["show_traveler_stat"] = False
    prepared["show_keeper_stat"] = show_keeper
    prepared["boosty_paid_chapters_count"] = boosty_paid_count
    prepared["show_boosty_paid_stat"] = boosty_paid_count > 0
    prepared["show_access_badge"] = bool(prepared.get("access_badge")) and not all_free

    # Для полностью бесплатной новеллы не показываем «Платно»,
    # даже если в служебном поле AccessModel осталось старое значение.
    if all_free:
        prepared["access_badge"] = None

    return prepared


def attach_chapter_counts_to_novels(novels: list[dict], chapters: list[dict], viewer_role: str = "guest") -> list[dict]:
    chapters_by_novel: dict[str, list[dict]] = {}
    for chapter in chapters:
        novel_id = clean_value(chapter.get("novel_id"))
        if novel_id:
            chapters_by_novel.setdefault(novel_id, []).append(chapter)
    result = []
    for novel in novels:
        prepared = prepare_novel_for_template(novel)
        novel_chapters = chapters_by_novel.get(clean_value(prepared.get("id")), [])
        prepared["required_role"] = novel_required_role(novel)
        prepared["display_chapters_count"] = count_chapter_units_for_card(novel_chapters) or prepared["total_chapters"] or 0
        prepared["free_chapters_count"] = count_available_chapter_units(novel_chapters, "guest")
        prepared["traveler_chapters_count"] = count_available_chapter_units(novel_chapters, "traveler")
        prepared["keeper_chapters_count"] = count_available_chapter_units(novel_chapters, "keeper")
        prepared["available_chapters_count"] = count_available_chapter_units(novel_chapters, viewer_role)
        prepared["viewer_has_book_access"] = viewer_can_access_required_role(viewer_role, prepared["required_role"])
        finalize_novel_access_summary(prepared)
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


def is_probably_direct_image_url(url: Any) -> bool:
    text = clean_value(url)

    if not text:
        return False

    lowered = text.split("?")[0].lower()

    return bool(
        re.search(r"\.(?:png|jpe?g|webp|gif|avif|svg)$", lowered)
        or "teletype.in/files/" in lowered
        or "telegra.ph/file/" in lowered
    )


def extract_first_image_from_html(page_url: str, html_text: str) -> str:
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)

        if match:
            src = html.unescape(clean_value(match.group(1)))

            if src:
                return urljoin(page_url, src)

    return ""


def resolve_external_image_url(url: Any) -> str:
    """Return a browser-displayable image URL.

    Fox images are stored in the Excel/Google Sheets tab `fox` as Teletype links.
    If the link is already a direct image URL, it is used as-is. If it is a
    Teletype/Telegraph page URL, the first page image is extracted and used.
    """
    text = clean_value(url)

    if not text:
        return ""

    if text.startswith("//"):
        text = f"https:{text}"

    if text.startswith("http://"):
        text = "https://" + text[len("http://"):]

    if is_probably_direct_image_url(text):
        return text

    parsed = urlparse(text)
    host = parsed.netloc.lower()

    if "teletype.in" not in host and "telegra.ph" not in host:
        return text

    try:
        response = requests.get(
            text,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()
    except Exception:
        return text

    extracted = extract_first_image_from_html(text, response.text)

    return extracted or text


def html_to_plain_text(fragment: str) -> str:
    text = re.sub(r"(?is)<br\s*/?>", "\n", fragment)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_chapter_service_block(fragment: str) -> bool:
    text = html_to_plain_text(fragment)
    normalized = text.lower().replace("ё", "е")

    if not normalized:
        return True

    if normalized in ("--", "—", "–", "***", "* * *"):
        return True

    footer_markers = (
        "перевод зефиркины",
        "перевод: зефиркины",
        "зефиркины баоцы",
        "зефиркины баоцзы",
        "спасибо что читаете с нами",
        "спасибо, что читаете с нами",
        "спасибо что читаете вместе с нами",
        "спасибо, что читаете вместе с нами",
        "купить полный перевод",
        "полный перевод boosty",
        "boosty/telegraph",
        "boosty / telegraph",
        "boosty / teletype",
        "boosty/teletype",
    )

    if any(marker in normalized for marker in footer_markers):
        return True

    # Часто в конце главы есть отдельная ссылка/пункт покупки полного перевода.
    # Удаляем именно короткий служебный блок, а не любое упоминание Boosty внутри текста.
    if len(normalized) <= 220 and ("boosty" in normalized or "telegraph" in normalized or "teletype" in normalized):
        if any(marker in normalized for marker in ("купить", "полный перевод", "подпис", "ранний доступ")):
            return True

    navigation_markers = (
        "к оглавлению",
        "оглавление",
        "следующая глава",
        "следующая",
        "прошлая глава",
        "предыдущая глава",
        "предыдущая",
        "назад",
        "вперед",
        "вперёд",
        "next chapter",
        "previous chapter",
        "contents",
    )

    if len(normalized) <= 160 and any(marker in normalized for marker in navigation_markers):
        return True

    return False


def clean_chapter_content_html(html_content: str) -> str:
    content = clean_value(html_content)

    if not content:
        return ""

    block_pattern = re.compile(
        r"(?is)<(p|h1|h2|h3|h4|blockquote|li|div|a)\b[^>]*>.*?</\1>"
    )

    def replace_block(match: re.Match) -> str:
        block = match.group(0)

        if is_chapter_service_block(block):
            return ""

        return block

    cleaned = block_pattern.sub(replace_block, content)

    # На всякий случай вычищаем хвосты, если они пришли не отдельным <p>, а текстом внутри блока.
    trailing_patterns = (
        r"(?is)<p[^>]*>\s*(?:--|—|–)\s*</p>\s*",
        r"(?is)<p[^>]*>\s*спасибо[, ]+что читаете(?: вместе)? с нами!?\s*(?:💙)?\s*</p>\s*",
        r"(?is)<p[^>]*>\s*перевод\s+зефиркины\s+бао[цз]ы.*?</p>\s*",
        r"(?is)<p[^>]*>.*?купить\s+полный\s+перевод.*?</p>\s*",
        r"(?is)<a[^>]*>.*?купить\s+полный\s+перевод.*?</a>\s*",
    )

    changed = True
    while changed:
        changed = False
        for pattern in trailing_patterns:
            updated = re.sub(pattern, "", cleaned).strip()
            if updated != cleaned:
                cleaned = updated
                changed = True

    cleaned = re.sub(r"(?is)<hr\s*/?>", "", cleaned)
    cleaned = re.sub(r"(?is)(?:\s|&nbsp;)*$", "", cleaned).strip()

    return cleaned


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
                safe_attrs.append(f'{html.escape(key_text)}="{html.escape(value_text)}"')
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
        response = requests.get(api_url, params={"return_content": "true"}, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        return None, f"Ошибка загрузки Telegraph: {error}"
    if not data.get("ok"):
        return None, data.get("error") or "Telegraph вернул ошибку."
    result = data.get("result") or {}
    raw_html = "".join(render_telegraph_node(node) for node in result.get("content") or [])
    html_content = clean_chapter_content_html(raw_html)
    return {"title": result.get("title") or "", "content_html": html_content}, ""



def extract_preview_text(html_content: str, max_sentences: int = 2, max_chars: int = 460) -> str:
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    text = " ".join(soup.stripped_strings)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    preview = " ".join(sentences[:max_sentences]).strip()
    if len(preview) > max_chars:
        preview = preview[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return preview


def fetch_locked_preview(chapter: dict) -> tuple[str, str]:
    url = chapter_preview_url(chapter)
    if not url:
        return "", ""
    content, error = fetch_telegraph_content(url)
    if error or not content:
        return "", error
    return extract_preview_text(content.get("content_html") or ""), ""


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
    normalized = {
        "chapter_id": clean_value(row.get("chapter_id")),
        "novel_id": to_int(row.get("novel_id"), 0),
        "volume_no": to_int(row.get("volume_no"), 0) if clean_value(row.get("volume_no")) else None,
        "volume_title": clean_value(row.get("volume_title")) or None,
        "chapter_no": clean_value(row.get("chapter_no")),
        "source_chapter_no": clean_value(row.get("source_chapter_no")) or clean_value(row.get("chapter_no")),
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


def get_fox() -> dict[str, str]:
    # Лисички берутся не из /static, а из таблицы fox,
    # которая синхронизируется из Excel/Google Sheets листа fox.
    # url может быть прямой ссылкой на картинку Teletype/Telegraph.
    default_fox = {
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


def get_all_novels(include_hidden: bool = False) -> list[dict]:
    if not supabase_ready():
        return []
    filters = None if include_hidden else {"miniapp_visible": "eq.true"}
    try:
        rows = db_select("novels", select="*", filters=filters, order="novel_id.asc")
        return [adapt_novel_from_db(row) for row in rows]
    except Exception as error:
        print("get_all_novels error:", error)
        return []


def get_all_chapters() -> list[dict]:
    if not supabase_ready():
        return []
    try:
        rows = db_select("chapters", select="*", order="novel_id.asc,chapter_no.asc")
        return [adapt_chapter_from_db(row) for row in rows]
    except Exception as error:
        print("get_all_chapters error:", error)
        return []


def get_novel_by_slug(slug: str, include_hidden: bool = False) -> dict | None:
    if not supabase_ready():
        return None
    filters = {"code": f"eq.{slug}"}
    if not include_hidden:
        filters["miniapp_visible"] = "eq.true"
    rows = db_select("novels", select="*", filters=filters, limit=1)
    return adapt_novel_from_db(rows[0]) if rows else None


def get_novel_chapters(novel_id: str) -> list[dict]:
    if not supabase_ready():
        return []
    rows = db_select("chapters", select="*", filters={"novel_id": f"eq.{novel_id}"}, order="chapter_no.asc")
    return [adapt_chapter_from_db(row) for row in rows]


def get_chapter_by_id(chapter_id: str) -> dict | None:
    if not supabase_ready():
        return None
    rows = db_select("chapters", select="*", filters={"chapter_id": f"eq.{chapter_id}"}, limit=1)
    return adapt_chapter_from_db(rows[0]) if rows else None


def get_novel_by_id(novel_id: str) -> dict | None:
    if not supabase_ready():
        return None
    rows = db_select("novels", select="*", filters={"novel_id": f"eq.{novel_id}"}, limit=1)
    return adapt_novel_from_db(rows[0]) if rows else None



# ============================================================================
# Unified access: Telegram groups + Tribute subscriptions + book entitlements
# ============================================================================

def parse_iso_datetime(value: Any) -> datetime | None:
    text = clean_value(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def telegram_membership_details(chat_id: str, user_id: int) -> dict[str, Any]:
    result = {
        "chat_id": chat_id or "",
        "configured": bool(TELEGRAM_BOT_TOKEN and chat_id),
        "ok": False,
        "active": False,
        "status": "not_configured",
        "description": "",
    }
    if not result["configured"]:
        return result
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChatMember",
            params={"chat_id": chat_id, "user_id": user_id},
            timeout=12,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as error:
        result.update(status="request_error", description=str(error))
        return result
    result["ok"] = bool(data.get("ok"))
    if not data.get("ok"):
        result.update(status="telegram_error", description=clean_value(data.get("description")))
        return result
    member = data.get("result") or {}
    result["status"] = clean_value(member.get("status")) or "unknown"
    result["active"] = telegram_member_is_active(member)
    result["is_member"] = member.get("is_member")
    return result


def get_active_tribute_subscriptions(user_id: int) -> list[dict[str, Any]]:
    if not supabase_ready() or not user_id:
        return []
    try:
        rows = db_select(
            "user_subscriptions",
            filters={"telegram_user_id": f"eq.{int(user_id)}"},
            order="expires_at.desc",
        )
    except Exception as error:
        print("Tribute subscription lookup failed:", error)
        return []
    now = utc_now()
    active = []
    for row in rows:
        expires = parse_iso_datetime(row.get("expires_at"))
        if row.get("status") not in {"active", "cancelling"}:
            continue
        if not expires or expires <= now:
            continue
        active.append(row)
    return active


def get_active_book_entitlements(user_id: int, novel_id: int | None = None) -> list[dict[str, Any]]:
    if not supabase_ready() or not user_id:
        return []
    filters = {"telegram_user_id": f"eq.{int(user_id)}", "revoked_at": "is.null"}
    if novel_id:
        filters["novel_id"] = f"eq.{int(novel_id)}"
    try:
        rows = db_select("user_entitlements", filters=filters, order="granted_at.desc")
    except Exception as error:
        print("Book entitlement lookup failed:", error)
        return []
    now = utc_now()
    return [
        row for row in rows
        if not row.get("expires_at") or (parse_iso_datetime(row.get("expires_at")) or now) > now
    ]


def tribute_role_from_rows(rows: list[dict[str, Any]]) -> str:
    roles = {clean_value(row.get("access_role")) for row in rows}
    if "keeper" in roles:
        return "keeper"
    if "traveler" in roles:
        return "traveler"
    return "guest"


def resolve_access_profile(user_id: int, novel_id: int | None = None, force_group_refresh: bool = False) -> dict[str, Any]:
    keeper_group = telegram_membership_details(KEEPER_CHAT_ID, user_id)
    traveler_group = telegram_membership_details(TRAVELER_CHAT_ID, user_id)
    tribute_rows = get_active_tribute_subscriptions(user_id)
    tribute_role = tribute_role_from_rows(tribute_rows)
    group_role = "keeper" if keeper_group["active"] else ("traveler" if traveler_group["active"] else "guest")
    global_role = max((group_role, tribute_role), key=role_rank)
    entitlements = get_active_book_entitlements(user_id, novel_id)
    full_book = any(clean_value(row.get("access_type")) == "full_book" for row in entitlements)
    return {
        "user_id": int(user_id),
        "role": global_role,
        "group_role": group_role,
        "tribute_role": tribute_role,
        "groups": {"traveler": traveler_group, "keeper": keeper_group},
        "tribute_subscriptions": tribute_rows,
        "book_entitlements": entitlements,
        "has_full_book_access": full_book,
        "novel_id": novel_id,
        "checked_at": utc_now().isoformat(),
    }


def resolve_telegram_role(user_id: int, force_refresh: bool = False) -> str:
    # Kept under the old name because authentication calls this function.
    profile = resolve_access_profile(user_id, force_group_refresh=force_refresh)
    return clean_value(profile.get("role")) or "guest"


def viewer_access_profile(viewer: dict[str, Any], novel_id: int | None = None) -> dict[str, Any]:
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return {
            "user_id": None, "role": "guest", "group_role": "guest", "tribute_role": "guest",
            "groups": {}, "tribute_subscriptions": [], "book_entitlements": [],
            "has_full_book_access": False, "novel_id": novel_id,
        }
    return resolve_access_profile(int(viewer["user_id"]), novel_id=novel_id)


def novel_is_gift(novel: dict) -> bool:
    """A gift novel is visible only to Traveler, Keeper or a book owner.

    The source of truth is the 🎁 marker in Legend.PostIcons. AccessModel is
    accepted only as a backward-compatible fallback.
    """
    icons = clean_value(novel.get("post_icons"))
    model = clean_value(novel.get("access_model")).lower()
    return "🎁" in icons or "boostyonly" in model or "boosty only" in model


def novel_is_traveler_only(novel: dict) -> bool:
    # Backward-compatible alias used by older templates/helpers.
    return novel_is_gift(novel)


def chapter_is_translated(chapter: dict) -> bool:
    return bool(clean_value(chapter.get("translation_date")))


def can_view_novel_for_profile(novel: dict, profile: dict[str, Any]) -> bool:
    if profile.get("has_full_book_access"):
        return True
    if not novel_is_gift(novel):
        return True
    return clean_value(profile.get("role")) in {"traveler", "keeper"}


def effective_role_for_novel(viewer: dict[str, Any], novel: dict) -> tuple[str, dict[str, Any]]:
    novel_id = to_int(novel.get("novel_id") or novel.get("id"), 0) or None
    profile = viewer_access_profile(viewer, novel_id)
    return clean_value(profile.get("role")) or "guest", profile


def chapter_content_url_for_access(chapter: dict, novel: dict, profile: dict[str, Any]) -> str:
    """Return the only URL the current user may receive.

    Rules:
    - Traveler only gains visibility of 🎁 novels; premium dates do not open chapters.
    - Keeper reads chapters after PremiumReleaseDate.
    - A full-book entitlement reads every translated chapter of that novel.
    - Everyone may read chapters after FreeReleaseDate.
    """
    role = clean_value(profile.get("role")) or "guest"

    # A planned row without TranslationDate is never readable.
    if not chapter_is_translated(chapter):
        return ""

    if profile.get("has_full_book_access"):
        return chapter_premium_url(chapter) or chapter_public_url(chapter)

    # Guests must not enter gift-only novels.
    if novel_is_gift(novel) and role == "guest":
        return ""

    # Keeper receives the scheduled premium release.
    if role == "keeper" and chapter_premium_ready(chapter):
        return chapter_premium_url(chapter)

    # Guest, Traveler and Keeper receive the ordinary free release.
    if chapter_public_ready(chapter):
        return chapter_public_url(chapter)

    return ""


def count_available_chapter_units_for_access(
    chapters: list[dict], novel: dict, profile: dict[str, Any]
) -> int:
    return len({
        chapter_unit_key(chapter)
        for chapter in chapters
        if chapter_content_url_for_access(chapter, novel, profile)
    })


def prepare_chapter_for_access_template(
    chapter: dict, novel: dict, profile: dict[str, Any]
) -> dict:
    role = clean_value(profile.get("role")) or "guest"
    item = prepare_chapter_for_template(chapter, role)
    url = chapter_content_url_for_access(chapter, novel, profile)
    item["url"] = url
    item["is_available"] = bool(url)

    if item["is_available"]:
        item["access_label"] = "Открыта"
        item["access_class"] = "chapter-access-public"
    elif not chapter_is_translated(chapter):
        item["access_label"] = "Ещё не переведена"
        item["access_class"] = "chapter-access-hidden"
    elif role == "keeper":
        item["access_label"] = "Откроется по расписанию"
        item["access_class"] = "chapter-access-keeper"
    else:
        item["access_label"] = "Откроется бесплатно позже"
        item["access_class"] = "chapter-access-locked"
    return item


def build_chapter_display_list_for_access(
    chapters: list[dict], novel: dict, profile: dict[str, Any]
) -> tuple[list[dict], int]:
    role = clean_value(profile.get("role")) or "guest"
    prepared = []
    for chapter in sort_chapters(chapters):
        # Rows without any Telegraph content are service/planning rows, not TOC items.
        if not chapter_has_readable_url(chapter):
            continue
        if chapter.get("is_visible") is not True and role != "keeper" and not profile.get("has_full_book_access"):
            continue
        prepared.append(prepare_chapter_for_access_template(chapter, novel, profile))

    locked_seen = 0
    hidden_locked_count = 0
    for item in prepared:
        item["is_paid_extra"] = False
        item["hidden"] = False
        if item.get("is_available"):
            continue
        locked_seen += 1
        if locked_seen > 3:
            item["is_paid_extra"] = True
            item["hidden"] = True
            hidden_locked_count += 1
    return prepared, hidden_locked_count


def get_chapter_index_info_for_access(
    chapters: list[dict], current_chapter_id: str, novel: dict, profile: dict[str, Any]
) -> dict:
    available = [
        prepare_chapter_for_access_template(chapter, novel, profile)
        for chapter in sort_chapters(chapters)
        if chapter_content_url_for_access(chapter, novel, profile)
    ]
    units = []
    seen_units = set()
    for chapter in available:
        key = chapter_unit_key(chapter)
        if key not in seen_units:
            seen_units.add(key)
            units.append({
                "unit_key": key,
                "chapter_id": chapter.get("chapter_id"),
                "chapter_title": chapter.get("title"),
            })
    current_index = next((i for i, unit in enumerate(units, 1)
                          if clean_value(unit.get("chapter_id")) == clean_value(current_chapter_id)), 0)
    return {"chapter_index": current_index, "available_chapters": len(units)}


def get_neighbor_chapters_for_access(
    chapters: list[dict], current_chapter_id: str, novel: dict, profile: dict[str, Any]
) -> tuple[dict | None, dict | None]:
    available = [
        prepare_chapter_for_access_template(chapter, novel, profile)
        for chapter in sort_chapters(chapters)
        if chapter_content_url_for_access(chapter, novel, profile)
    ]
    index = next((i for i, chapter in enumerate(available)
                  if clean_value(chapter.get("chapter_id")) == clean_value(current_chapter_id)), None)
    if index is None:
        return None, None
    return (available[index - 1] if index > 0 else None,
            available[index + 1] if index + 1 < len(available) else None)


def prepare_library_novels_for_access(
    novels: list[dict], chapters: list[dict], viewer: dict[str, Any]
) -> list[dict]:
    chapters_by_novel: dict[str, list[dict]] = {}
    for chapter in chapters:
        key = clean_value(chapter.get("novel_id"))
        if key:
            chapters_by_novel.setdefault(key, []).append(chapter)

    result = []
    for novel in novels:
        novel_id_text = clean_value(novel.get("novel_id") or novel.get("id"))
        novel_id = to_int(novel_id_text, 0) or None
        profile = viewer_access_profile(viewer, novel_id)
        if not can_view_novel_for_profile(novel, profile):
            continue

        novel_chapters = chapters_by_novel.get(novel_id_text, [])
        prepared = prepare_novel_for_template(novel)
        prepared["required_role"] = "traveler" if novel_is_gift(novel) else "guest"
        prepared["display_chapters_count"] = count_chapter_units_for_card(novel_chapters) or prepared["total_chapters"] or 0

        guest_profile = {"role": "guest", "has_full_book_access": False}
        keeper_profile = {"role": "keeper", "has_full_book_access": False}
        prepared["free_chapters_count"] = count_available_chapter_units_for_access(novel_chapters, novel, guest_profile)
        # Traveler chapter count intentionally equals free count. Its extra right is book visibility only.
        prepared["traveler_chapters_count"] = prepared["free_chapters_count"]
        prepared["keeper_chapters_count"] = count_available_chapter_units_for_access(novel_chapters, novel, keeper_profile)
        prepared["available_chapters_count"] = count_available_chapter_units_for_access(novel_chapters, novel, profile)
        prepared["viewer_has_book_access"] = can_view_novel_for_profile(novel, profile)
        prepared["viewer_has_full_book_access"] = bool(profile.get("has_full_book_access"))
        finalize_novel_access_summary(prepared)
        result.append(prepared)
    return result


def tribute_signature_valid(raw_body: bytes, signature: str) -> bool:
    if not TRIBUTE_API_KEY or not signature:
        return False
    signature = signature.strip()
    if signature.lower().startswith("sha256="):
        signature = signature.split("=", 1)[1]
    digest = hmac.new(TRIBUTE_API_KEY.encode("utf-8"), raw_body, hashlib.sha256).digest()
    return hmac.compare_digest(signature.lower(), digest.hex().lower()) or hmac.compare_digest(signature, base64.b64encode(digest).decode("ascii"))


def tribute_access_role(subscription_id: Any) -> str | None:
    value = clean_value(subscription_id)
    if value and value == TRIBUTE_KEEPER_SUBSCRIPTION_ID:
        return "keeper"
    if value and value == TRIBUTE_TRAVELER_SUBSCRIPTION_ID:
        return "traveler"
    return None


def payment_event_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def record_payment_event(provider: str, event_hash: str, event_name: str, payload: dict[str, Any], status: str, error: str | None = None) -> None:
    row = {
        "provider": provider,
        "event_hash": event_hash,
        "event_name": event_name,
        "telegram_user_id": to_int((payload.get("payload") or {}).get("telegram_user_id"), 0) or None,
        "external_plan_id": clean_value((payload.get("payload") or {}).get("subscription_id")) or None,
        "payload": payload,
        "status": status,
        "error_message": error,
        "processed_at": utc_now().isoformat() if status in {"processed", "ignored", "error"} else None,
    }
    try:
        db_upsert("payment_events", [row], "provider,event_hash", batch_size=1)
    except Exception as exc:
        print("Unable to record payment event:", exc)


def upsert_tribute_subscription(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    telegram_user_id = to_int(payload.get("telegram_user_id"), 0)
    subscription_id = clean_value(payload.get("subscription_id"))
    role = tribute_access_role(subscription_id)
    if not telegram_user_id or not subscription_id:
        raise ValueError("В webhook отсутствуют telegram_user_id или subscription_id")
    if not role:
        return {"status": "ignored", "reason": "unknown_subscription", "subscription_id": subscription_id}
    cancelled = event_name == "cancelled_subscription"
    row = {
        "telegram_user_id": telegram_user_id,
        "provider": "tribute",
        "external_plan_id": subscription_id,
        "access_role": role,
        "status": "cancelling" if cancelled else "active",
        "subscription_type": clean_value(payload.get("type")) or None,
        "auto_renew": not cancelled,
        "started_at": clean_value(payload.get("purchase_created_at") or payload.get("created_at")) or None,
        "expires_at": clean_value(payload.get("expires_at")) or utc_now().isoformat(),
        "cancelled_at": utc_now().isoformat() if cancelled else None,
        "renewed_at": utc_now().isoformat() if event_name == "renewed_subscription" else None,
        "telegram_username": clean_value(payload.get("telegram_username")) or None,
        "provider_user_id": clean_value(payload.get("trb_user_id")) or None,
    }
    db_upsert("user_subscriptions", [row], "telegram_user_id,provider,external_plan_id", batch_size=1)
    _membership_cache.pop(telegram_user_id, None)
    return {"status": "processed", "role": role, "telegram_user_id": telegram_user_id}

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "supabase": "ok" if supabase_ready() else "not_configured",
        "telegram_bot": "ok" if TELEGRAM_BOT_TOKEN else "not_configured",
        "traveler_chat": "ok" if TRAVELER_CHAT_ID else "not_configured",
        "keeper_chat": "ok" if KEEPER_CHAT_ID else "not_configured",
        "traveler_chat_id_normalized": bool(TRAVELER_CHAT_ID),
        "keeper_chat_id_normalized": bool(KEEPER_CHAT_ID),
        "tribute_webhook": "ok" if TRIBUTE_API_KEY else "not_configured",
        "tribute_traveler_plan": "ok" if TRIBUTE_TRAVELER_SUBSCRIPTION_ID else "not_configured",
        "tribute_keeper_plan": "ok" if TRIBUTE_KEEPER_SUBSCRIPTION_ID else "not_configured",
    }


@app.get("/")
async def home():
    return RedirectResponse(url="/library")


@app.get("/library")
async def library(request: Request):
    viewer = viewer_from_request(request)
    include_hidden = viewer.get("role") == "keeper"
    novels = get_all_novels(include_hidden=include_hidden)
    chapters = get_all_chapters()
    fox = get_fox()
    prepared_novels = prepare_library_novels_for_access(novels, chapters, viewer)
    return templates.TemplateResponse(
        request,
        "library.html",
        {"app_title": APP_TITLE, "novels": prepared_novels, "fox": fox, "viewer": public_viewer(viewer)},
    )


@app.get("/novel/{slug}")
async def novel_page(request: Request, slug: str):
    viewer = viewer_from_request(request)
    viewer_role = str(viewer.get("role") or "guest")
    novel = get_novel_by_slug(slug, include_hidden=viewer_role == "keeper")
    if not novel:
        raise HTTPException(status_code=404, detail="Новелла не найдена")
    if not to_bool(novel.get("is_visible"), True) and viewer_role != "keeper":
        raise HTTPException(status_code=404, detail="Новелла не найдена")
    viewer_role, access_profile = effective_role_for_novel(viewer, novel)
    if not can_view_novel_for_profile(novel, access_profile):
        raise HTTPException(status_code=403, detail="Эта новелла доступна подписчикам")
    fox = get_fox()
    all_chapters = get_novel_chapters(clean_value(novel.get("id")))
    prepared_novel = prepare_novel_for_template(novel)
    prepared_novel["required_role"] = novel_required_role(novel)
    prepared_novel["viewer_has_book_access"] = viewer_can_access_required_role(viewer_role, prepared_novel["required_role"])
    prepared_novel["display_chapters_count"] = count_chapter_units_for_card(all_chapters) or prepared_novel["total_chapters"] or 0
    prepared_novel["free_chapters_count"] = count_available_chapter_units_for_access(
        all_chapters, novel, {"role": "guest", "has_full_book_access": False}
    )
    prepared_novel["traveler_chapters_count"] = prepared_novel["free_chapters_count"]
    prepared_novel["keeper_chapters_count"] = count_available_chapter_units_for_access(
        all_chapters, novel, {"role": "keeper", "has_full_book_access": False}
    )
    prepared_novel["available_chapters_count"] = count_available_chapter_units_for_access(
        all_chapters, novel, access_profile
    )
    finalize_novel_access_summary(prepared_novel)
    visible_chapters = all_chapters if viewer_role == "keeper" else [chapter for chapter in all_chapters if chapter.get("is_visible") is True]
    display_chapters, hidden_subscriber_count = build_chapter_display_list_for_access(visible_chapters, novel, access_profile)
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
            "viewer": public_viewer(viewer),
            "access_profile": access_profile,
        },
    )


@app.get("/chapter/{chapter_id}")
async def chapter_page(request: Request, chapter_id: str):
    viewer = viewer_from_request(request)
    viewer_role = str(viewer.get("role") or "guest")
    chapter = get_chapter_by_id(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Глава не найдена")
    novel = get_novel_by_id(clean_value(chapter.get("novel_id")))
    if not novel:
        raise HTTPException(status_code=404, detail="Новелла главы не найдена")
    viewer_role, access_profile = effective_role_for_novel(viewer, novel)
    if not can_view_novel_for_profile(novel, access_profile):
        raise HTTPException(status_code=403, detail="Эта новелла доступна подписчикам")
    if not to_bool(novel.get("is_visible"), True) and viewer_role != "keeper":
        raise HTTPException(status_code=404, detail="Глава не найдена")

    all_chapters = get_novel_chapters(clean_value(novel.get("id")))
    prepared_chapter = prepare_chapter_for_template(chapter, viewer_role)
    prepared_novel = prepare_novel_for_template(novel)
    prepared_novel["required_role"] = novel_required_role(novel)
    previous_chapter, next_chapter = get_neighbor_chapters_for_access(all_chapters, clean_value(prepared_chapter.get("chapter_id")), novel, access_profile)
    index_info = get_chapter_index_info_for_access(all_chapters, clean_value(prepared_chapter.get("chapter_id")), novel, access_profile)
    url = chapter_content_url_for_access(chapter, novel, access_profile)
    is_locked = not bool(url)
    telegraph_content = None
    telegraph_error = ""
    preview_text = ""

    if url:
        telegraph_content, telegraph_error = fetch_telegraph_content(url)
    else:
        preview_text, preview_error = fetch_locked_preview(chapter)
        telegraph_error = preview_error if not preview_text else ""

    required_role = normalize_required_role(chapter.get("access_level"))
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
            "preview_text": preview_text,
            "required_role": required_role,
            "access_copy": access_copy(required_role),
            "boosty_access_url": clean_value(novel.get("boosty_premium_url")) or clean_value(novel.get("boosty_url")),
            "tribute_access_url": TRIBUTE_KEEPER_URL,
            "fox": fox,
            "viewer": public_viewer(viewer),
            "access_profile": access_profile,
        },
    )


@app.get("/api/fox")
async def api_fox():
    fox = get_fox()
    return {"status": "ok", "fox": fox}


@app.get("/api/library")
async def api_library(request: Request):
    viewer = viewer_from_request(request)
    viewer_role = str(viewer.get("role") or "guest")
    novels = get_all_novels(include_hidden=viewer_role == "keeper")
    chapters = get_all_chapters()
    prepared_novels = prepare_library_novels_for_access(novels, chapters, viewer)
    return {
        "status": "ok",
        "viewer": public_viewer(viewer),
        "novels_count": len(prepared_novels),
        "chapters_count": len(chapters),
        "novels_sample": prepared_novels,
    }


@app.get("/api/novel/{slug}")
async def api_novel(request: Request, slug: str):
    viewer = viewer_from_request(request)
    viewer_role = str(viewer.get("role") or "guest")
    novel = get_novel_by_slug(slug, include_hidden=viewer_role == "keeper")
    if not novel:
        raise HTTPException(status_code=404, detail="Новелла не найдена")
    chapters = get_novel_chapters(clean_value(novel.get("id")))
    viewer_role, access_profile = effective_role_for_novel(viewer, novel)
    if not can_view_novel_for_profile(novel, access_profile):
        raise HTTPException(status_code=403, detail="Эта новелла доступна подписчикам")
    return {
        "status": "ok",
        "viewer": public_viewer(viewer),
        "novel": prepare_novel_for_template(novel),
        "chapters": [prepare_chapter_for_access_template(chapter, novel, access_profile) for chapter in chapters],
    }



@app.get("/api/auth/me")
async def api_auth_me(request: Request):
    viewer = viewer_from_request(request)
    return {"status": "ok", "viewer": public_viewer(viewer)}


@app.post("/api/auth/telegram")
async def api_auth_telegram(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Ожидался JSON") from exc
    init_data = str(payload.get("init_data") or payload.get("initData") or "")
    if not init_data:
        raise HTTPException(status_code=400, detail="initData отсутствует")
    viewer = authenticate_telegram_viewer(init_data)
    response = JSONResponse({"status": "ok", "viewer": public_viewer(viewer)})
    response.set_cookie(
        AUTH_COOKIE_NAME,
        make_session_token(viewer),
        max_age=AUTH_SESSION_TTL_SECONDS,
        httponly=True,
        secure=APP_ENV == "production",
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/auth/logout")
async def api_auth_logout():
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response



@app.get("/api/auth/debug")
async def api_auth_debug(request: Request, refresh: bool = Query(default=False)):
    viewer = viewer_from_request(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return {
            "status": "ok",
            "authenticated": False,
            "message": "Telegram initData ещё не подтверждён.",
            "telegram": {"user_id": None, "first_name": "", "username": ""},
            "rights": {"role": "guest", "can_read_free": True, "can_read_traveler": False, "can_read_keeper": False},
        }
    profile = resolve_access_profile(int(viewer["user_id"]), force_group_refresh=refresh)
    role = clean_value(profile.get("role")) or "guest"
    return {
        "status": "ok",
        "authenticated": True,
        "telegram": {
            "user_id": viewer.get("user_id"),
            "first_name": viewer.get("first_name") or "",
            "username": viewer.get("username") or "",
        },
        "rights": {
            "role": role,
            "can_view_regular_books": True,
            "can_view_gift_books": role in {"traveler", "keeper"},
            "can_read_free_releases": True,
            "can_read_premium_releases": role == "keeper",
            "traveler_reads_premium": False,
            "book_entitlements_count": len(profile.get("book_entitlements") or []),
            "full_book_novel_ids": [
                row.get("novel_id")
                for row in (profile.get("book_entitlements") or [])
                if clean_value(row.get("access_type")) == "full_book"
            ],
        },
        "groups": profile.get("groups") or {},
        "tribute_subscriptions": profile.get("tribute_subscriptions") or [],
        "book_entitlements": profile.get("book_entitlements") or [],
        "configuration": {
            "traveler_chat_id": TRAVELER_CHAT_ID,
            "keeper_chat_id": KEEPER_CHAT_ID,
            "tribute_traveler_subscription_id": TRIBUTE_TRAVELER_SUBSCRIPTION_ID,
            "tribute_keeper_subscription_id": TRIBUTE_KEEPER_SUBSCRIPTION_ID,
            "tribute_webhook_configured": bool(TRIBUTE_API_KEY),
        },
        "checked_at": profile.get("checked_at"),
    }


@app.post("/api/webhooks/tribute")
async def tribute_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("trbt-signature", "")
    if not tribute_signature_valid(raw_body, signature):
        raise HTTPException(status_code=401, detail="Неверная подпись Tribute")
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Некорректный JSON Tribute") from exc
    event_name = clean_value(event.get("name"))
    payload = event.get("payload") or {}
    event_hash = payment_event_hash(raw_body)
    if event_name not in {"new_subscription", "renewed_subscription", "cancelled_subscription"}:
        record_payment_event("tribute", event_hash, event_name, event, "ignored")
        return {"status": "ok", "result": "ignored"}
    try:
        result = upsert_tribute_subscription(event_name, payload)
        record_payment_event("tribute", event_hash, event_name, event, result.get("status", "processed"))
        return {"status": "ok", "result": result}
    except Exception as error:
        record_payment_event("tribute", event_hash, event_name, event, "error", str(error))
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/admin/boosty/order")
async def import_boosty_order(request: Request, token: str | None = Query(default=None)):
    validate_sync_token(request, token)
    payload = await request.json()
    order_key = clean_value(payload.get("boosty_order_id"))
    product_key = clean_value(payload.get("boosty_bundle_key"))
    telegram_user_id = to_int(payload.get("telegram_user_id"), 0)
    if not order_key or not product_key or not telegram_user_id:
        raise HTTPException(status_code=400, detail="Нужны boosty_order_id, boosty_bundle_key и telegram_user_id")
    products = db_select("boosty_products", filters={"boosty_bundle_key": f"eq.{quote(product_key, safe='')}"}, limit=1)
    if not products:
        raise HTTPException(status_code=404, detail="Бандл не зарегистрирован в boosty_products")
    product = products[0]
    order_row = {
        "boosty_order_id": order_key,
        "boosty_bundle_key": product_key,
        "buyer_email": clean_value(payload.get("buyer_email")) or None,
        "buyer_name": clean_value(payload.get("buyer_name")) or None,
        "amount": payload.get("amount"),
        "currency": clean_value(payload.get("currency")) or None,
        "payment_status": "paid",
        "purchased_at": clean_value(payload.get("purchased_at")) or utc_now().isoformat(),
        "telegram_user_id": telegram_user_id,
        "claimed_at": utc_now().isoformat(),
        "raw_email": payload,
    }
    db_upsert("boosty_orders", [order_row], "boosty_order_id", batch_size=1)
    entitlement = {
        "telegram_user_id": telegram_user_id,
        "novel_id": product["novel_id"],
        "source_type": "boosty_bundle",
        "source_id": order_key,
        "access_type": product.get("access_type") or "full_book",
        "granted_at": utc_now().isoformat(),
        "metadata": {"boosty_bundle_key": product_key, "product_name": product.get("product_name")},
    }
    db_upsert("user_entitlements", [entitlement], "telegram_user_id,novel_id,source_type,source_id", batch_size=1)
    _membership_cache.pop(telegram_user_id, None)
    return {"status": "ok", "telegram_user_id": telegram_user_id, "novel_id": product["novel_id"]}


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
async def sync_from_sheets(request: Request, token: str | None = Query(default=None)):
    validate_sync_token(request, token)

    if not supabase_ready():
        return JSONResponse(
            {
                "status": "error",
                "stage": "configuration",
                "detail": "На Render не настроены SUPABASE_URL и SUPABASE_KEY/SUPABASE_SERVICE_KEY.",
            },
            status_code=500,
        )

    stage = "json"
    try:
        try:
            payload = await request.json()
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"Ожидался корректный JSON: {error}")

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Корень JSON должен быть объектом.")

        schema_version = to_int(payload.get("schema_version"), 0)
        if schema_version and schema_version != 17:
            raise HTTPException(status_code=409, detail=f"Неподдерживаемая версия схемы: {schema_version}. Ожидается 17.")

        stage = "normalization"
        novels_raw = payload.get("novels") or payload.get("Novels") or []
        chapters_raw = payload.get("chapters") or payload.get("Chapters") or []
        fox_raw = payload.get("fox") or payload.get("Fox") or []

        if isinstance(novels_raw, dict):
            novels_raw = list(novels_raw.values())
        if isinstance(chapters_raw, dict):
            chapters_raw = list(chapters_raw.values())
        if isinstance(fox_raw, dict):
            fox_raw = list(fox_raw.values())

        if not isinstance(novels_raw, list) or not isinstance(chapters_raw, list) or not isinstance(fox_raw, list):
            raise HTTPException(
                status_code=400,
                detail="Поля novels, chapters и fox должны быть массивами или объектами.",
            )

        novels = [normalize_novel_row(row) for row in novels_raw if isinstance(row, dict)]
        chapters = [normalize_chapter_row(row) for row in chapters_raw if isinstance(row, dict)]
        fox_rows = [normalize_fox_row(row) for row in fox_raw if isinstance(row, dict)]

        novels = [row for row in novels if to_int(row.get("novel_id"), 0) > 0 and clean_value(row.get("title_ru"))]
        chapters = [
            row for row in chapters
            if clean_value(row.get("chapter_id")) and to_int(row.get("novel_id"), 0) > 0
        ]
        fox_rows = [
            row for row in fox_rows
            if clean_value(row.get("name")) and clean_value(row.get("url"))
        ]

        release_warnings = [
            issue
            for chapter in chapters
            for issue in chapter_release_integrity_issues(chapter)
        ]

        result = {
            "status": "ok",
            "novels_received": len(novels),
            "chapters_received": len(chapters),
            "fox_received": len(fox_rows),
            "novels_upserted": 0,
            "chapters_upserted": 0,
            "fox_upserted": 0,
            "release_warnings_count": len(release_warnings),
            "release_warnings": release_warnings[:100],
        }

        stage = "novels"
        if novels:
            result["novels_upserted"] = db_upsert("novels", novels, "novel_id", batch_size=50)

        stage = "chapters"
        if chapters:
            result["chapters_upserted"] = db_upsert(
                "chapters",
                chapters,
                "chapter_id",
                batch_size=100,
            )

        stage = "fox"
        if fox_rows:
            result["fox_upserted"] = db_upsert("fox", fox_rows, "name", batch_size=50)

        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as error:
        # Render Logs получают полный traceback, а Apps Script — понятную причину.
        print("MiniApp sync failed at stage:", stage)
        traceback.print_exc()
        return JSONResponse(
            {
                "status": "error",
                "stage": stage,
                "detail": str(error),
            },
            status_code=500,
        )


@app.post("/api/sync")
async def sync_from_sheets_alias(request: Request, token: str | None = Query(default=None)):
    return await sync_from_sheets(request, token)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse(request, "index.html", {"app_title": APP_TITLE, "error": "Страница не найдена.", "fox": get_fox()}, status_code=404)
