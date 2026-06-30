from __future__ import annotations

import hmac
from typing import Any
from fastapi import HTTPException, Request
from .config import settings

MAX_JSON_BYTES = 2_000_000


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


def require_sync_token(token: str | None) -> None:
    if not settings.sync_token:
        raise HTTPException(status_code=503, detail="SYNC_TOKEN is not configured")
    if not token or not constant_time_equal(token, settings.sync_token):
        raise HTTPException(status_code=403, detail="Invalid token")


async def read_limited_json(request: Request) -> Any:
    body = await request.body()
    if len(body) > MAX_JSON_BYTES:
        raise HTTPException(status_code=413, detail="Request body is too large")
    if not body:
        return {}
    try:
        return await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
