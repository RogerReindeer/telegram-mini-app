"""Signed internal API for cross-database Reader Coins delivery from Qinghe."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from ..config import settings
from ..schemas_commerce import CoinGrantPayload
from ..security import read_limited_body
from ..services.coins import CoinGrantConflict, CoinGrantTemporaryError, credit_from_qinghe
from ..services.commerce_auth import INTERNAL_COMMERCE_BODY_LIMIT_BYTES, require_qinghe_signature

router = APIRouter(prefix="/api/internal/commerce", tags=["internal-commerce"])


@router.post("/coin-grants")
async def coin_grant(request: Request):
    raw_body = await read_limited_body(request, max_bytes=INTERNAL_COMMERCE_BODY_LIMIT_BYTES)
    require_qinghe_signature(request, raw_body)
    try:
        raw_payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="invalid_payload") from error
    try:
        model = CoinGrantPayload.model_validate(raw_payload)
    except ValidationError as error:
        raise HTTPException(status_code=400, detail="invalid_payload") from error

    if model.currency != "reader_coins":
        raise HTTPException(status_code=400, detail="unsupported_currency")
    if model.provider != "telegram_stars":
        raise HTTPException(status_code=400, detail="unsupported_provider")
    if model.amount > max(1, int(settings.reader_coin_max_single_grant or 1)):
        raise HTTPException(status_code=400, detail="grant_limit_exceeded")

    payload = model.model_dump()
    try:
        return credit_from_qinghe(payload)
    except CoinGrantConflict as error:
        raise HTTPException(status_code=409, detail="purchase_conflict") from error
    except CoinGrantTemporaryError as error:
        raise HTTPException(status_code=503, detail="temporary_error") from error
