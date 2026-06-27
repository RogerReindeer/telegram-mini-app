"""Routes for Translation CRM -> Supabase synchronization."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..security import SYNC_JSON_BODY_LIMIT_BYTES, read_json_payload, require_sync_token
from ..services.sync import build_validation_response, run_sync

router = APIRouter()


def validate_sync_token(request: Request, token: str | None) -> None:
    """Backward-compatible wrapper used by other admin routers."""
    require_sync_token(request, token)


@router.post("/sync")
async def sync_from_sheets(request: Request, token: str | None = Query(default=None)):
    validate_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=SYNC_JSON_BODY_LIMIT_BYTES)
    return await run_sync(payload)


@router.post("/api/sync")
async def sync_from_sheets_alias(request: Request, token: str | None = Query(default=None)):
    return await sync_from_sheets(request, token)


@router.post("/api/sync/validate")
async def validate_sync_payload_route(request: Request, token: str | None = Query(default=None)):
    validate_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=SYNC_JSON_BODY_LIMIT_BYTES)
    return build_validation_response(payload)


@router.post("/sync/validate")
async def validate_sync_payload_short_route(request: Request, token: str | None = Query(default=None)):
    return await validate_sync_payload_route(request, token)
