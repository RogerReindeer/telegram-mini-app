from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..security import SYNC_JSON_BODY_LIMIT_BYTES, read_json_payload, require_sync_token
from ..services.sync import build_validation_response, run_sync

router = APIRouter()


def _json_response_payload(response: Any) -> dict[str, Any]:
    if isinstance(response, JSONResponse):
        body = response.body.decode("utf-8") if isinstance(response.body, (bytes, bytearray)) else str(response.body)
        return json.loads(body or "{}")
    if isinstance(response, dict):
        return response
    return {}


@router.post("/api/sync")
async def api_sync(request: Request, token: str = ""):
    require_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=SYNC_JSON_BODY_LIMIT_BYTES)
    return await run_sync(payload)


@router.post("/sync")
async def legacy_sync(request: Request, token: str = ""):
    require_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=SYNC_JSON_BODY_LIMIT_BYTES)
    return await run_sync(payload)


@router.post("/api/sync/validate")
async def api_sync_validate(request: Request, token: str = ""):
    require_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=SYNC_JSON_BODY_LIMIT_BYTES)
    return build_validation_response(payload)


@router.post("/sync/validate")
async def legacy_sync_validate(request: Request, token: str = ""):
    require_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=SYNC_JSON_BODY_LIMIT_BYTES)
    return build_validation_response(payload)
