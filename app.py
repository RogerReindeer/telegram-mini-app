import os
import re
import html
import json
import hmac
import time
import base64
import hashlib
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
TRAVELER_CHAT_ID = (os.getenv("TRAVELER_CHAT_ID") or "").strip()
KEEPER_CHAT_ID = (os.getenv("KEEPER_CHAT_ID") or "").strip()
TRAVELER_JOIN_URL = (os.getenv("TRAVELER_JOIN_URL") or "").strip()
KEEPER_JOIN_URL = (os.getenv("KEEPER_JOIN_URL") or "").strip()
SESSION_SECRET = (os.getenv("SESSION_SECRET") or TELEGRAM_BOT_TOKEN or SYNC_TOKEN or "change-me").encode("utf-8")
AUTH_COOKIE_NAME = "zefirki_access"
AUTH_SESSION_TTL_SECONDS = int(os.getenv("AUTH_SESSION_TTL_SECONDS") or "900")
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = int(os.getenv("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS") or "86400")
MEMBERSHIP_CACHE_SECONDS = int(os.getenv("MEMBERSHIP_CACHE_SECONDS") or "300")
APP_ENV = (os.getenv("APP_ENV") or "production").lower()

ROLE_RANK = {"guest": 0, "traveler": 1, "keeper": 2}
ROLE_LABELS = {
    "guest": "Гость",
    "traveler": "🌱 Странствующий читатель",
    "keeper": "📜 Хранитель свитков",
}
_membership_cache: dict[int, tuple[float, dict[str, Any]]] = {}

NOVEL_TABLE_COLUMNS = {
    "id", "slug", "title", "title_en", "post_icons", "cover_url", "description", "tags",
    "top_description", "bottom_description", "original_language", "total_chapters",
    "translated_chapters", "progress_percent", "status", "access_model", "schedule_mode",
    "early_access_mode", "sort_order", "is_visible", "age_rating", "has_adult_badge",
    "translation_status", "translation_status_label", "translation_status_color", "relation_type",
    "relation_icon", "relation_color", "tags_short", "tags_tooltip", "added_date",
    "translation_author",
}

# ВАЖНО: в Supabase реальная колонка — chapter_code. В шаблоны мы отдаём chapter_id как алиас.
CHAPTER_TABLE_COLUMNS = {
    "chapter_code", "novel_id", "chapter_no", "title", "slug", "volume", "volume_no",
    "volume_title", "translation_date", "release_date", "free_release_date",
    "premium_release_date", "telegraph_url", "telegraph_free_url", "telegraph_premium_url",
    "telegraph_free_code", "telegraph_premium_code", "source_type", "access_level",
    "is_visible", "sort_order",
}

FOX_TABLE_COLUMNS = {"name", "url"}

KEY_MAP_NOVEL = {
    "NovelID": "id", "Slug": "slug", "Title": "title", "TitleEN": "title_en",
    "PostIcons": "post_icons", "CoverURL": "cover_url", "Description": "description",
    "Tags": "tags", "TopDescription": "top_description", "BottomDescription": "bottom_description",
    "OriginalLanguage": "original_language", "TotalChapters": "total_chapters",
    "TranslatedChapters": "translated_chapters", "ProgressPercent": "progress_percent",
    "Status": "status", "AccessModel": "access_model", "ScheduleMode": "schedule_mode",
    "EarlyAccessMode": "early_access_mode", "SortOrder": "sort_order", "IsVisible": "is_visible",
    "AgeRating": "age_rating", "HasAdultBadge": "has_adult_badge",
    "TranslationStatus": "translation_status", "TranslationStatusLabel": "translation_status_label",
    "TranslationStatusColor": "translation_status_color", "RelationType": "relation_type",
    "RelationIcon": "relation_icon", "RelationColor": "relation_color",
    "TagsShort": "tags_short", "TagsTooltip": "tags_tooltip", "AddedDate": "added_date",
    "TranslationAuthor": "translation_author",
}

KEY_MAP_CHAPTER = {
    "ChapterID": "chapter_code", "ChapterCode": "chapter_code", "chapter_id": "chapter_code",
    "chapter_code": "chapter_code", "NovelID": "novel_id", "ChapterNo": "chapter_no",
    "ChapterTitle": "title", "Slug": "slug", "Volume": "volume", "VolumeNo": "volume_no",
    "VolumeTitle": "volume_title", "TranslationDate": "translation_date", "ReleaseDate": "release_date",
    "FreeReleaseDate": "free_release_date", "PremiumReleaseDate": "premium_release_date",
    "TelegraphURL": "telegraph_url", "TelegraphFreeURL": "telegraph_free_url",
    "TelegraphPremiumURL": "telegraph_premium_url", "TelegraphFreeCode": "telegraph_free_code",
    "TelegraphPremiumCode": "telegraph_premium_code", "SourceType": "source_type",
    "AccessLevel": "access_level", "IsVisible": "is_visible", "SortOrder": "sort_order",
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
        "role": role,
        "role_label": ROLE_LABELS.get(role, ROLE_LABELS["guest"]),
        "traveler_join_url": TRAVELER_JOIN_URL,
        "keeper_join_url": KEEPER_JOIN_URL,
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


def resolve_telegram_role(user_id: int) -> str:
    cached = _membership_cache.get(user_id)
    now = time.time()
    if cached and cached[0] > now:
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


def authenticate_telegram_viewer(init_data: str) -> dict[str, Any]:
    user = validate_telegram_init_data(init_data)
    user_id = int(user["id"])
    role = resolve_telegram_role(user_id)
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
    return (
        clean_value(chapter.get("telegraph_premium_url"))
        or clean_value(chapter.get("telegraph_url"))
        or clean_value(chapter.get("telegraph_free_url"))
    )


def chapter_public_ready(chapter: dict) -> bool:
    if not chapter_public_url(chapter):
        return False
    release = clean_value(chapter.get("free_release_date"))
    return not release or is_date_open(release)


def chapter_premium_ready(chapter: dict) -> bool:
    if not chapter_premium_url(chapter):
        return False
    release = clean_value(chapter.get("premium_release_date"))
    return not release or is_date_open(release)


def chapter_content_url_for_role(chapter: dict, viewer_role: str) -> str:
    required = normalize_required_role(chapter.get("access_level"))
    if viewer_role == "keeper":
        return chapter_premium_url(chapter)
    if chapter.get("is_visible") is not True:
        return ""
    if chapter_public_ready(chapter):
        return chapter_public_url(chapter)
    if viewer_role == "traveler" and required == "traveler" and chapter_premium_ready(chapter):
        return chapter_premium_url(chapter)
    return ""


def chapter_preview_url(chapter: dict) -> str:
    if chapter.get("is_visible") is not True:
        return ""
    release = clean_value(chapter.get("premium_release_date"))
    if release and not is_date_open(release):
        return ""
    return chapter_premium_url(chapter)


def access_copy(required_role: str) -> dict[str, str]:
    if required_role == "keeper":
        return {
            "title": "Продолжение доступно Хранителю свитков",
            "description": "Хранитель свитков открывает абсолютно все главы и все книги читалки.",
        }
    return {
        "title": "Продолжение доступно по подписке",
        "description": "🌱 Странствующий читатель открывает главы подписки Boosty. 📜 Хранитель свитков открывает абсолютно всё.",
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


def db_upsert(table: str, rows: list[dict], conflict_key: str) -> list[dict]:
    if not rows:
        return []
    result = supabase_request(
        "POST",
        table,
        params={"on_conflict": conflict_key},
        payload=rows,
        prefer="resolution=merge-duplicates,return=representation",
    )
    return result if isinstance(result, list) else []


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
    return {"completed": "Завершено", "paused": "На передержке", "soon": "Скоро", "in_progress": "В процессе перевода"}.get(status, "В процессе перевода")


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


def chapter_code_value(chapter: dict) -> str:
    return clean_value(chapter.get("chapter_code")) or clean_value(chapter.get("chapter_id"))


def chapter_unit_key(chapter: dict) -> str:
    novel_id = clean_value(chapter.get("novel_id"))
    chapter_no = normalize_chapter_no_for_unit(chapter.get("chapter_no"))
    return f"{novel_id}:{chapter_no or chapter_code_value(chapter)}"


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
    prepared["title"] = clean_value(chapter.get("title")) or f"Глава {prepared['chapter_no']}"
    prepared["display_title"] = prepared["title"]
    prepared["required_role"] = required_role
    prepared["url"] = choose_chapter_url(chapter, viewer_role)
    prepared["is_available"] = bool(prepared["url"])
    prepared["viewer_role"] = viewer_role

    if prepared["is_available"]:
        if required_role == "guest":
            prepared["access_label"] = "🌱 Открыта"
        elif viewer_role == "keeper":
            prepared["access_label"] = "📜 Доступ Хранителя"
        else:
            prepared["access_label"] = "🌱 Доступ по подписке"
        prepared["access_class"] = "chapter-access-public"
    elif required_role == "traveler":
        prepared["access_label"] = "🌱 Странствующий читатель"
        prepared["access_class"] = "chapter-access-locked"
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

    hidden_locked_count = 0
    has_reached_open_block = False
    for chapter in prepared:
        is_locked = not chapter.get("is_available")
        chapter["is_paid_extra"] = False
        chapter["hidden"] = False
        if chapter.get("is_available"):
            has_reached_open_block = True
            continue
        # Locked chapters at the beginning remain visible. Locked chapters after
        # the first readable block are collapsed under the reveal button.
        if is_locked and has_reached_open_block:
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

def prepare_novel_for_template(novel: dict) -> dict:
    prepared = dict(novel)
    title = clean_value(novel.get("title"))
    post_icons = clean_value(novel.get("post_icons"))
    tags = clean_value(novel.get("tags"))
    tag_items = prepare_tag_items(tags)
    card_tag_items = build_card_tag_items(tag_items)
    translation_status = normalize_translation_status(novel.get("translation_status") or novel.get("status"), novel.get("translation_status_label"))
    progress_percent = normalize_progress_percent(novel.get("progress_percent"))
    prepared.update({
        "id": clean_value(novel.get("id")),
        "slug": clean_value(novel.get("slug")) or normalize_slug(title),
        "title": title,
        "display_title": compact_title_with_icons(post_icons, title),
        "title_en": clean_value(novel.get("title_en")),
        "post_icons": post_icons,
        "cover_url": clean_value(novel.get("cover_url")),
        "description": clean_value(novel.get("description")),
        "description_paragraphs": split_text_paragraphs(novel.get("description")),
        "top_description": clean_value(novel.get("top_description")),
        "bottom_description": clean_value(novel.get("bottom_description")),
        "tags": tags,
        "tag_items": tag_items,
        "catalog_tag_items": card_tag_items[:4],
        "card_tag_items": card_tag_items[:4],
        "catalog_hidden_tags": max(0, len(card_tag_items) - 4),
        "age_rating": clean_value(novel.get("age_rating")) or get_age_rating_from_tags(tags),
        "total_chapters": to_int(novel.get("total_chapters"), 0),
        "translated_chapters": to_int(novel.get("translated_chapters"), 0),
        "progress_percent": progress_percent,
        "normalized_progress_percent": progress_percent,
        "translation_status": translation_status,
        "translation_status_label": translation_status_label(translation_status, novel.get("translation_status_label")),
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


def normalize_novel_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_NOVEL)
    title = clean_value(row.get("title"))
    row["id"] = clean_value(row.get("id")) or clean_value(row.get("novel_id"))
    row["slug"] = clean_value(row.get("slug")) or normalize_slug(title or row["id"])
    row["title"] = title
    for key in ("title_en", "post_icons", "cover_url", "description", "tags", "top_description", "bottom_description", "original_language", "status", "access_model", "schedule_mode", "early_access_mode", "relation_type", "relation_icon", "relation_color", "tags_short", "tags_tooltip", "translation_author"):
        row[key] = clean_value(row.get(key))
    row["total_chapters"] = to_int(row.get("total_chapters"), 0)
    row["translated_chapters"] = to_int(row.get("translated_chapters"), 0)
    row["progress_percent"] = normalize_progress_percent(row.get("progress_percent"))
    row["translation_status"] = normalize_translation_status(row.get("translation_status") or row.get("status"), row.get("translation_status_label"))
    row["translation_status_label"] = translation_status_label(row["translation_status"], row.get("translation_status_label"))
    row["translation_status_color"] = translation_status_color(row["translation_status"], row.get("translation_status_color"))
    row["sort_order"] = to_float(row.get("sort_order"), to_float(row.get("id"), 999999))
    row["is_visible"] = to_bool(row.get("is_visible"), True)
    row["age_rating"] = clean_value(row.get("age_rating")) or get_age_rating_from_tags(row["tags"])
    row["has_adult_badge"] = to_bool(row.get("has_adult_badge"), False) or row["age_rating"] in ("18+", "21+", "NC-17", "R")
    row["added_date"] = parse_date(row.get("added_date"))
    return filter_columns(row, NOVEL_TABLE_COLUMNS)


def normalize_chapter_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_CHAPTER)
    chapter_code = clean_value(row.get("chapter_code"))
    novel_id = clean_value(row.get("novel_id"))
    chapter_no = clean_value(row.get("chapter_no"))
    row["chapter_code"] = chapter_code or f"{novel_id}-{chapter_no}"
    row["novel_id"] = novel_id
    row["chapter_no"] = chapter_no
    row["title"] = clean_value(row.get("title")) or f"Глава {chapter_no}"
    row["slug"] = clean_value(row.get("slug")) or normalize_slug(f"{novel_id}-{chapter_no}-{row['title']}")
    for key in ("volume", "volume_no", "volume_title", "telegraph_url", "telegraph_free_url", "telegraph_premium_url", "telegraph_free_code", "telegraph_premium_code"):
        row[key] = clean_value(row.get(key))
    for key in ("translation_date", "release_date", "free_release_date", "premium_release_date"):
        row[key] = parse_date(row.get(key))
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
    has_any_url = bool(row["telegraph_url"] or row["telegraph_free_url"] or row["telegraph_premium_url"])
    row["is_visible"] = to_bool(row.get("is_visible"), has_any_url)
    row["sort_order"] = to_float(row.get("sort_order"), parse_chapter_no_number(chapter_no))
    return filter_columns(row, CHAPTER_TABLE_COLUMNS)


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
    filters = None if include_hidden else {"is_visible": "eq.true"}
    try:
        return db_select("novels", select="*", filters=filters, order="sort_order.asc,id.asc")
    except Exception as error:
        print("get_all_novels error:", error)
        return []


def get_all_chapters() -> list[dict]:
    if not supabase_ready():
        return []
    try:
        return db_select("chapters", select="*", order="novel_id.asc,sort_order.asc,chapter_no.asc")
    except Exception as error:
        print("get_all_chapters error:", error)
        return []


def get_novel_by_slug(slug: str, include_hidden: bool = False) -> dict | None:
    if not supabase_ready():
        return None
    filters = {"slug": f"eq.{slug}"}
    if not include_hidden:
        filters["is_visible"] = "eq.true"
    rows = db_select("novels", select="*", filters=filters, limit=1)
    return rows[0] if rows else None


def get_novel_chapters(novel_id: str) -> list[dict]:
    if not supabase_ready():
        return []
    return db_select("chapters", select="*", filters={"novel_id": f"eq.{novel_id}"}, order="sort_order.asc,chapter_no.asc")


def get_chapter_by_id(chapter_id: str) -> dict | None:
    if not supabase_ready():
        return None
    rows = db_select("chapters", select="*", filters={"chapter_code": f"eq.{chapter_id}"}, limit=1)
    return rows[0] if rows else None


def get_novel_by_id(novel_id: str) -> dict | None:
    if not supabase_ready():
        return None
    rows = db_select("novels", select="*", filters={"id": f"eq.{novel_id}"}, limit=1)
    return rows[0] if rows else None


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "supabase": "ok" if supabase_ready() else "not_configured",
        "telegram_bot": "ok" if TELEGRAM_BOT_TOKEN else "not_configured",
        "traveler_chat": "ok" if TRAVELER_CHAT_ID else "not_configured",
        "keeper_chat": "ok" if KEEPER_CHAT_ID else "not_configured",
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
    prepared_novels = attach_chapter_counts_to_novels(novels, chapters, str(viewer.get("role") or "guest"))
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
    fox = get_fox()
    all_chapters = get_novel_chapters(clean_value(novel.get("id")))
    prepared_novel = prepare_novel_for_template(novel)
    prepared_novel["required_role"] = novel_required_role(novel)
    prepared_novel["viewer_has_book_access"] = viewer_can_access_required_role(viewer_role, prepared_novel["required_role"])
    prepared_novel["display_chapters_count"] = count_chapter_units_for_card(all_chapters) or prepared_novel["total_chapters"] or 0
    prepared_novel["free_chapters_count"] = count_available_chapter_units(all_chapters, "guest")
    prepared_novel["traveler_chapters_count"] = count_available_chapter_units(all_chapters, "traveler")
    prepared_novel["keeper_chapters_count"] = count_available_chapter_units(all_chapters, "keeper")
    prepared_novel["available_chapters_count"] = count_available_chapter_units(all_chapters, viewer_role)
    visible_chapters = all_chapters if viewer_role == "keeper" else [chapter for chapter in all_chapters if chapter.get("is_visible") is True]
    display_chapters, hidden_subscriber_count = build_chapter_display_list(visible_chapters, viewer_role)
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
        raise HTTPException(status_code=404, detail="Книга главы не найдена")
    if not to_bool(novel.get("is_visible"), True) and viewer_role != "keeper":
        raise HTTPException(status_code=404, detail="Глава не найдена")

    all_chapters = get_novel_chapters(clean_value(novel.get("id")))
    prepared_chapter = prepare_chapter_for_template(chapter, viewer_role)
    prepared_novel = prepare_novel_for_template(novel)
    prepared_novel["required_role"] = novel_required_role(novel)
    previous_chapter, next_chapter = get_neighbor_chapters(all_chapters, clean_value(prepared_chapter.get("chapter_id")), viewer_role)
    index_info = get_chapter_index_info(all_chapters, clean_value(prepared_chapter.get("chapter_id")), viewer_role)
    url = choose_chapter_url(chapter, viewer_role)
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
            "fox": fox,
            "viewer": public_viewer(viewer),
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
    prepared_novels = attach_chapter_counts_to_novels(novels, chapters, viewer_role)
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
    return {
        "status": "ok",
        "viewer": public_viewer(viewer),
        "novel": prepare_novel_for_template(novel),
        "chapters": [prepare_chapter_for_template(chapter, viewer_role) for chapter in chapters],
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
    novels = [normalize_novel_row(row) for row in novels_raw if isinstance(row, dict)]
    chapters = [normalize_chapter_row(row) for row in chapters_raw if isinstance(row, dict)]
    fox_rows = [normalize_fox_row(row) for row in fox_raw if isinstance(row, dict)]
    novels = [row for row in novels if clean_value(row.get("id")) and clean_value(row.get("title"))]
    chapters = [row for row in chapters if clean_value(row.get("chapter_code")) and clean_value(row.get("novel_id"))]
    fox_rows = [row for row in fox_rows if clean_value(row.get("name")) and clean_value(row.get("url"))]
    result = {"status": "ok", "novels_received": len(novels), "chapters_received": len(chapters), "fox_received": len(fox_rows), "novels_upserted": 0, "chapters_upserted": 0, "fox_upserted": 0}
    if novels:
        result["novels_upserted"] = len(db_upsert("novels", novels, "id"))
    if chapters:
        result["chapters_upserted"] = len(db_upsert("chapters", chapters, "chapter_code"))
    if fox_rows:
        result["fox_upserted"] = len(db_upsert("fox", fox_rows, "name"))
    return result


@app.post("/api/sync")
async def sync_from_sheets_alias(request: Request, token: str | None = Query(default=None)):
    return await sync_from_sheets(request, token)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse(request, "index.html", {"app_title": APP_TITLE, "error": "Страница не найдена.", "fox": get_fox()}, status_code=404)
