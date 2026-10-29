from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..database import SupabaseError
from ..security import WEBHOOK_BODY_LIMIT_BYTES, read_json_payload, require_sync_token
from ..services.payments import (
    PaymentConflictError,
    PaymentPayloadError,
    PaymentProductNotFoundError,
    import_boosty_order,
)

router = APIRouter()

@router.post("/api/admin/boosty/order")
async def boosty_order(request: Request):
    require_sync_token(request)
    payload = await read_json_payload(request, max_bytes=WEBHOOK_BODY_LIMIT_BYTES)
    try:
        return await run_in_threadpool(import_boosty_order, payload)
    except PaymentPayloadError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except PaymentProductNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PaymentConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SupabaseError as error:
        raise HTTPException(status_code=503, detail="payment_storage_temporarily_unavailable") from error
