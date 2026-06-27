"""Routes for Translation CRM -> Supabase synchronization."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..security import SYNC_JSON_BODY_LIMIT_BYTES, read_json_payload, require_sync_token
from ..services.sync import build_validation_response, run_sync
from ..services.events import record_event

router = APIRouter()


def validate_sync_token(request: Request, token: str | None) -> None:
    """Backward-compatible wrapper used by other admin routers."""
    require_sync_token(request, token)


def _json_response_payload(response: object) -> dict:
    """Best-effort JSONResponse body reader for operational logging only.

    run_sync() intentionally returns JSONResponse for both success and handled
    errors. The router must not call dict methods on that response object,
    otherwise a handled sync problem turns into an opaque HTTP 500.
    """
    if isinstance(response, JSONResponse):
        try:
            raw = getattr(response, "body", b"") or b""
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return response if isinstance(response, dict) else {}


@router.post("/sync")
async def sync_from_sheets(request: Request, token: str | None = Query(default=None)):
    validate_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=SYNC_JSON_BODY_LIMIT_BYTES)
    record_event("sync_started", novels=len(payload.get("novels") or []), chapters=len(payload.get("chapters") or []))
    response = await run_sync(payload)
    result = _json_response_payload(response)
    record_event(
        "sync_finished",
        status=str(result.get("status") or ("error" if isinstance(response, JSONResponse) and response.status_code >= 400 else "ok")),
        sync_id=result.get("sync_id"),
        warnings_count=result.get("warnings_count"),
        stage=result.get("stage"),
    )
    return response


@router.post("/api/sync")
async def sync_from_sheets_alias(request: Request, token: str | None = Query(default=None)):
    return await sync_from_sheets(request, token)


@router.post("/api/sync/validate")
async def validate_sync_payload_route(request: Request, token: str | None = Query(default=None)):
    validate_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=SYNC_JSON_BODY_LIMIT_BYTES)
    result = build_validation_response(payload)
    record_event("sync_validate", status=str(result.get("status") or "ok"), errors_count=result.get("errors_count"), warnings_count=result.get("warnings_count"))
    return result


@router.post("/sync/validate")
async def validate_sync_payload_short_route(request: Request, token: str | None = Query(default=None)):
    return await validate_sync_payload_route(request, token)
