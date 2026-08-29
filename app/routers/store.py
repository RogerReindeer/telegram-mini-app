"""Reader Coins user-facing endpoints.

v242 intentionally exposes only the wallet. Content purchases are not enabled in
this foundation release.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..services.auth import viewer_from_request
from ..services.coins import CoinGrantTemporaryError, get_wallet

router = APIRouter(prefix="/api/store", tags=["reader-coins"])


@router.get("/wallet")
def wallet(request: Request):
    if not settings.reader_coins_enabled:
        raise HTTPException(status_code=404, detail="reader_coins_disabled")
    viewer = viewer_from_request(request)
    if viewer.get("admin_preview"):
        return {
            "status": "ok",
            "currency": "reader_coins",
            "balance": 0,
            "lifetime_credited": 0,
            "lifetime_spent": 0,
            "read_only": True,
        }
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        raise HTTPException(status_code=401, detail="Откройте приложение внутри Telegram")
    try:
        data = get_wallet(int(viewer["user_id"]))
    except CoinGrantTemporaryError as error:
        raise HTTPException(status_code=503, detail="wallet_temporarily_unavailable") from error
    return {"status": "ok", "currency": "reader_coins", "read_only": False, **data}
