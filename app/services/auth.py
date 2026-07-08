"""Telegram authentication and access profile service.

This module owns the parts that are easy to break when they are scattered
through page handlers: Telegram initData validation, signed session cookies,
Telegram group membership, active Tribute subscriptions and book entitlements.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl

import requests
from fastapi import HTTPException, Request

from ..config import settings
from ..database import db_select, db_upsert, supabase_ready
from ..utils import clean_value, to_int, utc_now

ROLE_RANK = {"guest": 0, "traveler": 1, "keeper": 2}
AUTH_COOKIE_NAME = "zefirki_access"
AUTH_SESSION_TTL_SECONDS = int(os.getenv("AUTH_SESSION_TTL_SECONDS") or "900")
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = int(os.getenv("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS") or "86400")
MEMBERSHIP_CACHE_SECONDS = int(os.getenv("MEMBERSHIP_CACHE_SECONDS") or "300")
APP_ENV = settings.app_env

TELEGRAM_BOT_TOKEN = settings.telegram_bot_token
SYNC_TOKEN = settings.sync_token
SESSION_SECRET_TEXT = settings.session_secret or TELEGRAM_BOT_TOKEN or SYNC_TOKEN or secrets.token_hex(32)
SESSION_SECRET = SESSION_SECRET_TEXT.encode("utf-8")

TRAVELER_CHAT_ID = settings.normalized_traveler_chat_id
KEEPER_CHAT_ID = settings.normalized_keeper_chat_id

TRIBUTE_API_KEY = settings.tribute_api_key
TRIBUTE_TRAVELER_SUBSCRIPTION_ID = settings.tribute_traveler_subscription_id
TRIBUTE_KEEPER_SUBSCRIPTION_ID = settings.tribute_keeper_subscription_id
TRIBUTE_TRAVELER_URL = settings.tribute_traveler_url
TRIBUTE_KEEPER_URL = settings.tribute_keeper_url
ACCESS_DEBUG_ENABLED = settings.access_debug_enabled

_membership_cache: dict[int, tuple[float, dict[str, Any]]] = {}


def normalize_telegram_chat_id(value: Any) -> str:
    """Normalize Telegram group IDs copied with or without the -100 prefix."""
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


def require_authenticated_viewer(request: Request) -> dict[str, Any]:
    viewer = viewer_from_request(request)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        raise HTTPException(status_code=401, detail="Откройте приложение внутри Telegram")
    return viewer


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


def parse_iso_datetime(value: Any) -> datetime | None:
    text = clean_value(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_active_tribute_subscriptions(user_id: int) -> tuple[list[dict[str, Any]], bool]:
    """Returns (active_rows, ok). ok=False means the lookup itself failed
    (transient Supabase error), as opposed to legitimately having no active
    subscription — callers must not treat a failed lookup as "no access"."""
    if not supabase_ready() or not user_id:
        return [], True
    try:
        rows = db_select(
            "user_subscriptions",
            filters={"telegram_user_id": f"eq.{int(user_id)}"},
            order="expires_at.desc",
        )
    except Exception as error:
        print("Tribute subscription lookup failed:", error)
        return [], False
    now = utc_now()
    active = []
    for row in rows:
        expires = parse_iso_datetime(row.get("expires_at"))
        if row.get("status") not in {"active", "cancelling"}:
            continue
        if not expires or expires <= now:
            continue
        active.append(row)
    return active, True


def get_active_book_entitlements(user_id: int, novel_id: int | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Returns (active_rows, ok); see get_active_tribute_subscriptions."""
    if not supabase_ready() or not user_id:
        return [], True
    filters = {"telegram_user_id": f"eq.{int(user_id)}", "revoked_at": "is.null"}
    if novel_id:
        filters["novel_id"] = f"eq.{int(novel_id)}"
    try:
        rows = db_select("user_entitlements", filters=filters, order="granted_at.desc")
    except Exception as error:
        print("Book entitlement lookup failed:", error)
        return [], False
    now = utc_now()
    active = [
        row for row in rows
        if not row.get("expires_at") or (parse_iso_datetime(row.get("expires_at")) or now) > now
    ]
    return active, True


def tribute_role_from_rows(rows: list[dict[str, Any]]) -> str:
    roles = {clean_value(row.get("access_role")) for row in rows}
    if "keeper" in roles:
        return "keeper"
    if "traveler" in roles:
        return "traveler"
    return "guest"


def resolve_access_profile(
    user_id: int,
    novel_id: int | None = None,
    force_group_refresh: bool = False,
) -> dict[str, Any]:
    cached = _membership_cache.get(int(user_id))
    now_ts = time.time()
    if not force_group_refresh and cached and cached[0] > now_ts:
        cached_profile = dict(cached[1])
        if novel_id:
            entitlements, entitlements_ok = get_active_book_entitlements(user_id, novel_id)
            if entitlements_ok:
                cached_profile["book_entitlements"] = entitlements
                cached_profile["has_full_book_access"] = any(
                    clean_value(row.get("access_type")) == "full_book" for row in entitlements
                )
            cached_profile["novel_id"] = novel_id
        return cached_profile

    keeper_group = telegram_membership_details(KEEPER_CHAT_ID, user_id)
    traveler_group = telegram_membership_details(TRAVELER_CHAT_ID, user_id)
    tribute_rows, tribute_ok = get_active_tribute_subscriptions(user_id)
    entitlements, entitlements_ok = get_active_book_entitlements(user_id, novel_id)

    # Transient failures (Telegram API timeout, Supabase hiccup) must not
    # silently downgrade a paying Keeper/Traveler to guest. If any lookup
    # failed and we still have a previous profile (even expired), keep
    # serving it instead of computing a profile from partial/missing data.
    lookup_failed = (
        keeper_group.get("status") == "request_error"
        or traveler_group.get("status") == "request_error"
        or not tribute_ok
        or not entitlements_ok
    )
    if lookup_failed and cached:
        stale_profile = dict(cached[1])
        if novel_id:
            stale_profile["novel_id"] = novel_id
        return stale_profile

    tribute_role = tribute_role_from_rows(tribute_rows)
    group_role = "keeper" if keeper_group["active"] else ("traveler" if traveler_group["active"] else "guest")
    global_role = max((group_role, tribute_role), key=role_rank)
    full_book = any(clean_value(row.get("access_type")) == "full_book" for row in entitlements)
    profile = {
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
    _membership_cache[int(user_id)] = (now_ts + MEMBERSHIP_CACHE_SECONDS, dict(profile))
    return profile


def invalidate_access_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _membership_cache.clear()
        return
    _membership_cache.pop(int(user_id), None)


def resolve_telegram_role(user_id: int, force_refresh: bool = False) -> str:
    profile = resolve_access_profile(user_id, force_group_refresh=force_refresh)
    return clean_value(profile.get("role")) or "guest"


def viewer_access_profile(viewer: dict[str, Any], novel_id: int | None = None) -> dict[str, Any]:
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return {
            "user_id": None,
            "role": "guest",
            "group_role": "guest",
            "tribute_role": "guest",
            "groups": {},
            "tribute_subscriptions": [],
            "book_entitlements": [],
            "has_full_book_access": False,
            "novel_id": novel_id,
        }
    return resolve_access_profile(int(viewer["user_id"]), novel_id=novel_id)


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
