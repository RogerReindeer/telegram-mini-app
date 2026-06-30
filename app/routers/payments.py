from __future__ import annotations

from fastapi import APIRouter, Request

from ..security import WEBHOOK_BODY_LIMIT_BYTES, read_json_payload, read_limited_body, require_sync_token
from ..services.payments import import_boosty_order, process_tribute_webhook

router = APIRouter()


@router.post("/api/webhooks/tribute")
async def tribute_webhook(request: Request):
    raw_body = await read_limited_body(request, max_bytes=WEBHOOK_BODY_LIMIT_BYTES)
    signature = request.headers.get("x-tribute-signature") or request.headers.get("X-Tribute-Signature") or ""
    return process_tribute_webhook(raw_body, signature)


@router.post("/api/admin/boosty/order")
async def boosty_order(request: Request, token: str = ""):
    require_sync_token(request, token)
    payload = await read_json_payload(request, max_bytes=WEBHOOK_BODY_LIMIT_BYTES)
    return import_boosty_order(payload)
