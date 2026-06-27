"""Payment provider routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from .sync import validate_sync_token
from ..security import WEBHOOK_BODY_LIMIT_BYTES, read_json_payload, read_limited_body
from ..services.payments import import_boosty_order, process_tribute_webhook

router = APIRouter()


@router.post("/api/webhooks/tribute")
async def tribute_webhook(request: Request):
    raw_body = await read_limited_body(request, max_bytes=WEBHOOK_BODY_LIMIT_BYTES)
    signature = request.headers.get("trbt-signature", "")

    try:
        return process_tribute_webhook(raw_body, signature)
    except PermissionError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/api/admin/boosty/order")
async def boosty_order_import(request: Request, token: str | None = Query(default=None)):
    validate_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=WEBHOOK_BODY_LIMIT_BYTES)

    try:
        return import_boosty_order(payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
