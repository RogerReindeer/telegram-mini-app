"""Small security helpers shared by routers.

The goal is to keep token checks and JSON body handling consistent. Routers
should not compare secrets with plain equality and should not accept unlimited
request bodies from public endpoints.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request

from .config import settings

DEFAULT_JSON_BODY_LIMIT_BYTES = 512 * 1024
SYNC_JSON_BODY_LIMIT_BYTES = 2 * 1024 * 1024
WEBHOOK_BODY_LIMIT_BYTES = 512 * 1024
ADMIN_COOKIE_NAME = "zefirki_admin"
READER_PREVIEW_COOKIE_NAME = "zefirki_reader_preview"


def constant_time_equals(left: str | None, right: str | None) -> bool:
    """Compare secrets without leaking length/timing information."""
    left_text = left or ""
    right_text = right or ""
    if not left_text or not right_text:
        return False
    return hmac.compare_digest(left_text.encode("utf-8"), right_text.encode("utf-8"))


def bearer_token_from_header(value: str | None) -> str:
    text = (value or "").strip()
    if text.lower().startswith("bearer "):
        return text[7:].strip()
    return ""


def token_from_request(request: Request, query_token: str | None = None) -> str:
    """Read the sync token from header/Bearer and legacy query fallback."""
    header_token = request.headers.get("x-sync-token") or request.headers.get("X-Sync-Token") or ""
    bearer = bearer_token_from_header(
        request.headers.get("authorization") or request.headers.get("Authorization")
    )
    return (query_token or header_token or bearer or "").strip()


def require_sync_token(request: Request, query_token: str | None = None) -> None:
    """Validate SYNC_TOKEN with constant-time comparison."""
    if not settings.sync_token:
        raise HTTPException(status_code=503, detail="SYNC_TOKEN не настроен")
    if not constant_time_equals(token_from_request(request, query_token), settings.sync_token):
        raise HTTPException(status_code=403, detail="Неверный sync token")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _admin_signing_key() -> bytes:
    # SESSION_SECRET is already required in production. Keep ADMIN_TOKEN as a
    # secondary fallback so a local/dev admin login can still work independently
    # from the Telegram bot token.
    secret = settings.session_secret or settings.admin_token or "change-admin-secret"
    return hashlib.sha256(("admin-session:" + secret).encode("utf-8")).digest()


def make_admin_session_token() -> str:
    payload = {
        "scope": "admin",
        "exp": int(time.time()) + max(300, int(settings.admin_session_ttl_seconds or 43200)),
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64url_encode(hmac.new(_admin_signing_key(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def valid_admin_session_token(token: str | None) -> bool:
    text = (token or "").strip()
    if not text or "." not in text:
        return False
    body, signature = text.split(".", 1)
    expected = _b64url_encode(hmac.new(_admin_signing_key(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return payload.get("scope") == "admin" and int(payload.get("exp") or 0) >= int(time.time())




def make_reader_preview_session_token() -> str:
    payload = {
        "scope": "reader_preview",
        "exp": int(time.time()) + max(300, int(settings.admin_session_ttl_seconds or 43200)),
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    key = hashlib.sha256(("reader-preview:" + (settings.session_secret or settings.reader_preview_token or "change-reader-preview-secret")).encode("utf-8")).digest()
    signature = _b64url_encode(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def valid_reader_preview_session_token(token: str | None) -> bool:
    text = (token or "").strip()
    if not text or "." not in text:
        return False
    body, signature = text.split(".", 1)
    key = hashlib.sha256(("reader-preview:" + (settings.session_secret or settings.reader_preview_token or "change-reader-preview-secret")).encode("utf-8")).digest()
    expected = _b64url_encode(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return payload.get("scope") == "reader_preview" and int(payload.get("exp") or 0) >= int(time.time())


def admin_token_from_request(request: Request) -> str:
    header_token = request.headers.get("x-admin-token") or request.headers.get("X-Admin-Token") or ""
    bearer = bearer_token_from_header(
        request.headers.get("authorization") or request.headers.get("Authorization")
    )
    return (header_token or bearer or "").strip()


def admin_request_is_authorized(request: Request) -> bool:
    if not settings.admin_token:
        return False
    direct = admin_token_from_request(request)
    if direct and constant_time_equals(direct, settings.admin_token):
        return True
    return valid_admin_session_token(request.cookies.get(ADMIN_COOKIE_NAME, ""))


def require_admin_token(request: Request) -> None:
    """Require ADMIN_TOKEN or an HttpOnly signed admin session cookie."""
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN не настроен")
    if not admin_request_is_authorized(request):
        raise HTTPException(status_code=403, detail="Требуется вход администратора")


def _content_length(request: Request) -> int | None:
    value = request.headers.get("content-length")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


async def read_limited_body(request: Request, *, max_bytes: int) -> bytes:
    """Read request body with a conservative size limit."""
    limit = max(1, int(max_bytes or DEFAULT_JSON_BODY_LIMIT_BYTES))
    declared_size = _content_length(request)
    if declared_size is not None and declared_size > limit:
        raise HTTPException(status_code=413, detail="Тело запроса слишком большое")
    body = await request.body()
    if len(body) > limit:
        raise HTTPException(status_code=413, detail="Тело запроса слишком большое")
    return body


async def read_json_payload(
    request: Request,
    *,
    max_bytes: int = DEFAULT_JSON_BODY_LIMIT_BYTES,
    require_object: bool = True,
) -> Any:
    """Read JSON with size limit and a friendly 400 response."""
    body = await read_limited_body(request, max_bytes=max_bytes)
    if not body:
        raise HTTPException(status_code=400, detail="Ожидался JSON, но тело запроса пустое")
    try:
        payload = json.loads(body.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=400, detail="JSON должен быть в UTF-8") from error
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail=f"Ожидался корректный JSON: {error.msg}") from error
    if require_object and not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Ожидался JSON-объект")
    return payload
