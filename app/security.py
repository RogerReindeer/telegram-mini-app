"""Small security helpers shared by routers.

The goal is to keep token checks and JSON body handling consistent.  Routers
should not compare secrets with plain equality and should not accept unlimited
request bodies from public endpoints.
"""

from __future__ import annotations

import hmac
import json
from typing import Any

from fastapi import HTTPException, Request

from .config import settings

DEFAULT_JSON_BODY_LIMIT_BYTES = 512 * 1024
SYNC_JSON_BODY_LIMIT_BYTES = 2 * 1024 * 1024
WEBHOOK_BODY_LIMIT_BYTES = 512 * 1024


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
    """Read an admin/sync token from query, header, or Authorization bearer."""
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
