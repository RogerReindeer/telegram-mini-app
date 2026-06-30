from __future__ import annotations
from fastapi import APIRouter, Query
from ..security import require_sync_token
from ..services.payments import handle_tribute_webhook, import_boosty_order
router = APIRouter()
@router.post('/api/webhooks/tribute')
def tribute(payload: dict): return handle_tribute_webhook(payload)
@router.post('/api/admin/boosty/order')
def boosty(payload: dict, token: str | None = Query(default=None)):
    require_sync_token(token)
    return import_boosty_order(payload)
