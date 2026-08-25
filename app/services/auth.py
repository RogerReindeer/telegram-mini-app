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
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl

import requests
from fastapi import HTTPException, Request

from ..config import settings
from ..database import db_select, db_upsert, supabase_ready
from ..security import ADMIN_COOKIE_NAME, READER_PREVIEW_COOKIE_NAME, valid_admin_session_token, valid_reader_preview_session_token
from ..utils import clean_value, to_int, utc_now

ROLE_RANK = {"guest": 0, "traveler": 1, "subscriber": 1, "subscription": 1, "boosty": 1, "reader": 1, "keeper": 2, "premium": 2, "paid": 2, "early": 2}
AUTH_COOKIE_NAME = "zefirki_access"
AUTH_SESSION_TTL_SECONDS = int(os.getenv("AUTH_SESSION_TTL_SECONDS") or "900")
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = int(os.getenv("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS") or "86400")
MEMBERSHIP_CACHE_SECONDS = int(os.getenv("MEMBERSHIP_CACHE_SECONDS") or "300")
APP_ENV = settings.app_env

TELEGRAM_BOT_TOKEN = settings.telegram_bot_token
SESSION_SECRET_TEXT = settings.session_secret or TELEGRAM_BOT_TOKEN or "change-me"
SESSION_SECRET = SESSION_SECRET_TEXT.encode("utf-8")

MAIN_CHAT_ID = settings.normalized_main_chat_id
TRAVELER_CHAT_ID = settings.normalized_traveler_chat_id
KEEPER_CHAT_ID = settings.normalized_keeper_chat_id
TRAVELER_CHAT_IDS = settings.traveler_chat_ids or tuple(filter(None, (TRAVELER_CHAT_ID,)))
KEEPER_CHAT_IDS = settings.keeper_chat_ids or tuple(filter(None, (KEEPER_CHAT_ID,)))

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
    text = str(role or "guest").strip().lower()
    if not text:
        return 0
    if text in ROLE_RANK:
        return ROLE_RANK[text]
    if any(marker in text for marker in ("подпис", "boosty", "traveler", "reader", "subscriber")):
        return ROLE_RANK["traveler"]
    if any(marker in text for marker in ("keeper", "хранител", "premium", "paid", "early")):
        return ROLE_RANK["keeper"]
    return 0


def public_viewer(viewer: dict[str, Any]) -> dict[str, Any]:
    role = str(viewer.get("role") or "guest")
    return {
        "authenticated": bool(viewer.get("authenticated")),
        "user_id": viewer.get("user_id"),
        "first_name": viewer.get("first_name") or "",
        "username": viewer.get("username") or "",
        "role": role,
        "app_access": bool(viewer.get("app_access")),
        "app_access_source": str(viewer.get("app_access_source") or ""),
        "auth_version": int(viewer.get("auth_version") or 0),
        "admin_preview": bool(viewer.get("admin_preview")),
    }


def admin_preview_viewer(*, source: str = "admin_session") -> dict[str, Any]:
    """Return a read-only owner identity backed by the HttpOnly admin session.

    The owner must be able to QA the reader in an ordinary browser after
    /admin/login, without fabricating a Telegram user id or polluting reading
    progress/analytics. The preview gets Keeper-level content access plus
    full-book access, but user-state writes are handled as explicit no-ops.
    """
    return {
        "authenticated": True,
        "user_id": None,
        "first_name": "Администратор",
        "username": "",
        "role": "keeper",
        "app_access": True,
        "app_access_source": source,
        "auth_version": 3,
        "admin_preview": True,
    }


def viewer_has_app_identity(viewer: dict[str, Any]) -> bool:
    """True for a Telegram identity or the signed owner browser preview."""
    return bool(
        viewer.get("authenticated")
        and (viewer.get("user_id") or viewer.get("admin_preview"))
        and viewer.get("app_access")
    )


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
        "app_access": bool(viewer.get("app_access")),
        "app_access_source": str(viewer.get("app_access_source") or ""),
        "auth_version": 2,
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
    app_access_payload = payload.get("app_access")
    app_access = bool(app_access_payload) if app_access_payload is not None else role_rank(role) >= role_rank("traveler")
    return {
        "authenticated": True,
        "user_id": int(payload.get("user_id")),
        "first_name": str(payload.get("first_name") or ""),
        "username": str(payload.get("username") or ""),
        "role": role,
        "app_access": app_access,
        "app_access_source": str(payload.get("app_access_source") or ("subscription" if app_access else "")),
        "auth_version": int(payload.get("auth_version") or 0),
    }


def viewer_from_request(request: Request) -> dict[str, Any]:
    # Owner preview wins over a stale/guest Telegram cookie in the same browser.
    # This keeps /admin/login useful for browser QA even after the site has been
    # opened previously outside Telegram.
    if valid_admin_session_token(request.cookies.get(ADMIN_COOKIE_NAME, "")):
        return admin_preview_viewer()
    if valid_reader_preview_session_token(request.cookies.get(READER_PREVIEW_COOKIE_NAME, "")):
        return admin_preview_viewer(source="reader_preview")
    session = parse_session_token(request.cookies.get(AUTH_COOKIE_NAME, ""))
    if session:
        return session
    # A successful /admin/login creates a separate signed HttpOnly cookie.
    # It deliberately unlocks browser QA of the reader without creating a fake
    # Telegram identity or mixing owner activity into reader statistics.
    return {
        "authenticated": False,
        "user_id": None,
        "first_name": "",
        "username": "",
        "role": "guest",
        "app_access": False,
        "app_access_source": "",
        "auth_version": 0,
        "admin_preview": False,
    }


def require_authenticated_viewer(request: Request) -> dict[str, Any]:
    viewer = viewer_from_request(request)
    if not viewer.get("authenticated") or (not viewer.get("user_id") and not viewer.get("admin_preview")):
        raise HTTPException(status_code=401, detail="Откройте приложение внутри Telegram")
    return viewer


def require_app_access_viewer(request: Request) -> dict[str, Any]:
    """Require Telegram reader access or the signed owner browser session."""
    viewer = require_authenticated_viewer(request)
    if not viewer.get("app_access"):
        raise HTTPException(
            status_code=403,
            detail="Читалка доступна участникам основной группы или пользователям с активной подпиской",
        )
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


def telegram_membership_details(chat_id: str, user_id: int, *, label: str = "", source: str = "", role: str = "") -> dict[str, Any]:
    result = {
        "chat_id": chat_id or "",
        "label": label or chat_id or "",
        "source": source or "telegram",
        "role": role or "",
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




def telegram_memberships_for_role(chat_ids: tuple[str, ...], user_id: int, *, role: str) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for index, chat_id in enumerate(chat_ids):
        label = "📜 Хранитель свитков" if role == "keeper" else "🌱 Странствующий читатель"
        source = "tribute" if index == 0 else "boosty" if index == 1 else f"group_{index + 1}"
        details.append(telegram_membership_details(chat_id, user_id, label=label, source=source, role=role))
    return details


def first_active_group(groups: list[dict[str, Any]]) -> dict[str, Any] | None:
    for group in groups:
        if group.get("active"):
            return group
    return None

def parse_iso_datetime(value: Any) -> datetime | None:
    text = clean_value(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


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



def public_subscription_summary(
    viewer: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the user's effective paid subscription for Settings → Access.

    A paid level can be confirmed in two independent ways:
    1. a live subscription row received from Tribute;
    2. current membership in one of the configured paid Telegram groups.

    Telegram ``getChatMember`` does not expose a join/purchase date or an
    expiry date.  For a group-only subscription we therefore report that the
    access is membership-backed instead of inventing dates.
    """
    if viewer.get("admin_preview"):
        return {
            "active": False,
            "role": "keeper",
            "label": "Режим администратора",
            "subscriptions": [],
            "admin_preview": True,
        }
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return {"active": False, "role": "guest", "label": "Нет подписок", "subscriptions": []}

    user_id = int(viewer["user_id"])
    profile = dict(profile or {})
    if "tribute_subscriptions" in profile:
        rows = list(profile.get("tribute_subscriptions") or [])
    else:
        rows = get_active_tribute_subscriptions(user_id)

    labels = {
        "traveler": "🌱 Странствующий читатель",
        "keeper": "📜 Хранитель свитков",
    }

    def sort_key(row: dict[str, Any]) -> tuple[int, float]:
        expires = parse_iso_datetime(row.get("expires_at"))
        expires_ts = expires.timestamp() if expires else 0.0
        return (role_rank(row.get("access_role")), expires_ts)

    subscriptions: list[dict[str, Any]] = []
    for row in sorted(rows, key=sort_key, reverse=True):
        role = clean_value(row.get("access_role")) or "traveler"
        subscriptions.append({
            "active": True,
            "role": role,
            "label": labels.get(role, role),
            "started_at": clean_value(row.get("started_at")),
            "expires_at": clean_value(row.get("expires_at")),
            "status": clean_value(row.get("status")) or "active",
            "auto_renew": bool(row.get("auto_renew")),
            "provider": clean_value(row.get("provider")) or "tribute",
            "membership_based": False,
        })

    # If the payment webhook did not create a row (for example access is
    # granted by a Boosty/Telegram group), membership is still a valid active
    # subscription signal.  Prefer the strongest currently active paid group.
    groups = profile.get("groups") or {}
    active_paid_groups: list[dict[str, Any]] = []
    for role, key in (("keeper", "keepers"), ("traveler", "travelers")):
        role_groups = groups.get(key)
        if not isinstance(role_groups, list):
            single = groups.get("keeper" if role == "keeper" else "traveler")
            role_groups = [single] if isinstance(single, dict) else []
        for group in role_groups:
            if isinstance(group, dict) and group.get("active"):
                item = dict(group)
                item["role"] = role
                active_paid_groups.append(item)

    known_roles = {clean_value(item.get("role")) for item in subscriptions}
    for group in sorted(active_paid_groups, key=lambda item: role_rank(item.get("role")), reverse=True):
        role = clean_value(group.get("role")) or "traveler"
        if role in known_roles:
            continue
        source = clean_value(group.get("source")) or "telegram_group"
        source_labels = {
            "tribute": "Telegram-группа Tribute",
            "boosty": "Telegram-группа Boosty",
            "telegram": "Telegram-группа",
            "telegram_group": "Telegram-группа",
        }
        subscriptions.append({
            "active": True,
            "role": role,
            "label": labels.get(role, role),
            "started_at": "",
            "expires_at": "",
            "status": "active",
            "auto_renew": False,
            "provider": source,
            "provider_label": source_labels.get(source, "Telegram-группа"),
            "membership_based": True,
        })
        known_roles.add(role)

    # Backward-compatible fallback: the signed session already contains the
    # effective paid role calculated at Telegram authentication time.  This is
    # useful when the Access tab is opened during a transient Telegram API
    # failure but the user's current session has already verified the group.
    profile_role = clean_value(profile.get("role")) or "guest"
    session_role = clean_value(viewer.get("role")) or "guest"
    effective_role = max((profile_role, session_role), key=role_rank)
    if not subscriptions and role_rank(effective_role) >= role_rank("traveler"):
        subscriptions.append({
            "active": True,
            "role": effective_role,
            "label": labels.get(effective_role, effective_role),
            "started_at": "",
            "expires_at": "",
            "status": "active",
            "auto_renew": False,
            "provider": "verified_access",
            "provider_label": "Подтверждённый доступ",
            "membership_based": True,
        })

    if not subscriptions:
        return {"active": False, "role": "guest", "label": "Нет подписок", "subscriptions": []}

    def summary_sort_key(item: dict[str, Any]) -> tuple[int, int, float]:
        expires = parse_iso_datetime(item.get("expires_at"))
        return (
            role_rank(item.get("role")),
            1 if not item.get("membership_based") else 0,
            expires.timestamp() if expires else 0.0,
        )

    subscriptions.sort(key=summary_sort_key, reverse=True)
    strongest = dict(subscriptions[0])
    strongest["subscriptions"] = subscriptions
    return strongest


def get_active_book_entitlements(user_id: int, novel_id: int | None = None) -> list[dict[str, Any]]:
    if not supabase_ready() or not user_id:
        return []

    # Do not filter on revoked_at in PostgREST. Older production schemas did
    # not have this column, which made every entitlement lookup fail closed.
    # The v237 migration adds the column, while this local filter keeps the
    # code backward-compatible during deployment.
    filters = {"telegram_user_id": f"eq.{int(user_id)}"}
    if novel_id:
        filters["novel_id"] = f"eq.{int(novel_id)}"
    try:
        rows = db_select("user_entitlements", filters=filters, order="granted_at.desc")
    except Exception as error:
        print("Book entitlement lookup failed:", error)
        return []
    now = utc_now()
    active: list[dict[str, Any]] = []
    for row in rows:
        if clean_value(row.get("revoked_at")):
            continue
        expires_at = clean_value(row.get("expires_at"))
        if expires_at:
            expires = parse_iso_datetime(expires_at)
            if not expires or expires <= now:
                continue
        active.append(row)
    return active


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
            entitlements = get_active_book_entitlements(user_id, novel_id)
            cached_profile["book_entitlements"] = entitlements
            cached_profile["has_full_book_access"] = any(
                clean_value(row.get("access_type")) == "full_book" for row in entitlements
            )
            cached_profile["novel_id"] = novel_id
        return cached_profile

    # Telegram membership checks are independent network calls. Run the main,
    # traveler and keeper checks in parallel so a slow getChatMember response
    # does not multiply the login latency by the number of configured groups.
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="telegram-membership") as executor:
        main_future = executor.submit(
            telegram_membership_details,
            MAIN_CHAT_ID,
            user_id,
            label="Основная группа",
            source="main_group",
            role="member",
        )
        keeper_future = executor.submit(telegram_memberships_for_role, KEEPER_CHAT_IDS, user_id, role="keeper")
        traveler_future = executor.submit(telegram_memberships_for_role, TRAVELER_CHAT_IDS, user_id, role="traveler")
        main_group = main_future.result()
        keeper_groups = keeper_future.result()
        traveler_groups = traveler_future.result()
    keeper_group = first_active_group(keeper_groups) or (keeper_groups[0] if keeper_groups else telegram_membership_details("", user_id, label="📜 Хранитель свитков", role="keeper"))
    traveler_group = first_active_group(traveler_groups) or (traveler_groups[0] if traveler_groups else telegram_membership_details("", user_id, label="🌱 Странствующий читатель", role="traveler"))
    tribute_rows = get_active_tribute_subscriptions(user_id)
    tribute_role = tribute_role_from_rows(tribute_rows)
    group_role = "keeper" if any(group.get("active") for group in keeper_groups) else ("traveler" if any(group.get("active") for group in traveler_groups) else "guest")
    global_role = max((group_role, tribute_role), key=role_rank)
    has_subscription = role_rank(global_role) >= role_rank("traveler")
    main_group_active = bool(main_group.get("active"))
    app_access = main_group_active or has_subscription
    app_access_source = (
        "main_group+subscription" if main_group_active and has_subscription
        else "main_group" if main_group_active
        else "subscription" if has_subscription
        else ""
    )
    entitlements = get_active_book_entitlements(user_id, novel_id)
    full_book = any(clean_value(row.get("access_type")) == "full_book" for row in entitlements)
    profile = {
        "user_id": int(user_id),
        "role": global_role,
        "group_role": group_role,
        "tribute_role": tribute_role,
        "groups": {"main": main_group, "traveler": traveler_group, "keeper": keeper_group, "travelers": traveler_groups, "keepers": keeper_groups},
        "app_access": app_access,
        "app_access_source": app_access_source,
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



def viewer_fast_access_profile(viewer: dict[str, Any], novel_id: int | None = None) -> dict[str, Any]:
    """Build a page-render access profile without network calls.

    Telegram group membership is already reflected in the signed session cookie
    after /api/auth/telegram or /api/auth/me. Page rendering must not call
    Telegram getChatMember synchronously, otherwise opening a novel TOC can wait
    for several external requests. This fast profile is intentionally used only
    for normal HTML page rendering; explicit access refresh endpoints still use
    viewer_access_profile(..., force_group_refresh=True).
    """
    if viewer.get("admin_preview"):
        return {
            "user_id": None,
            "role": "keeper",
            "app_access": True,
            "app_access_source": clean_value(viewer.get("app_access_source")) or "admin_session",
            "group_role": "keeper",
            "tribute_role": "guest",
            "groups": {},
            "tribute_subscriptions": [],
            "book_entitlements": [],
            "has_full_book_access": True,
            "novel_id": novel_id,
            "fast_page_profile": True,
            "admin_preview": True,
        }
    role = clean_value(viewer.get("role")) or "guest"
    user_id = to_int(viewer.get("user_id") or viewer.get("telegram_user_id"), 0)
    entitlements = get_active_book_entitlements(user_id, novel_id) if user_id and novel_id else []
    full_book = any(clean_value(row.get("access_type")) == "full_book" for row in entitlements)
    return {
        "user_id": user_id or None,
        "role": role if role in ROLE_RANK else "guest",
        "app_access": bool(viewer.get("app_access")),
        "app_access_source": clean_value(viewer.get("app_access_source")),
        "group_role": role if role in ROLE_RANK else "guest",
        "tribute_role": "guest",
        "groups": {},
        "tribute_subscriptions": [],
        "book_entitlements": entitlements,
        "has_full_book_access": full_book,
        "novel_id": novel_id,
        "fast_page_profile": True,
    }

def viewer_access_profile(viewer: dict[str, Any], novel_id: int | None = None, force_group_refresh: bool = False) -> dict[str, Any]:
    if viewer.get("admin_preview"):
        return viewer_fast_access_profile(viewer, novel_id)
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        return {
            "user_id": None,
            "role": "guest",
            "app_access": False,
            "app_access_source": "",
            "group_role": "guest",
            "tribute_role": "guest",
            "groups": {},
            "tribute_subscriptions": [],
            "book_entitlements": [],
            "has_full_book_access": False,
            "novel_id": novel_id,
        }
    return resolve_access_profile(int(viewer["user_id"]), novel_id=novel_id, force_group_refresh=force_group_refresh)


def authenticate_telegram_viewer(init_data: str, force_refresh: bool = True) -> dict[str, Any]:
    user = validate_telegram_init_data(init_data)
    user_id = int(user["id"])
    profile = resolve_access_profile(user_id, force_group_refresh=force_refresh)
    return {
        "authenticated": True,
        "user_id": user_id,
        "first_name": str(user.get("first_name") or ""),
        "username": str(user.get("username") or ""),
        "role": clean_value(profile.get("role")) or "guest",
        "app_access": bool(profile.get("app_access")),
        "app_access_source": clean_value(profile.get("app_access_source")),
        "auth_version": 2,
    }
