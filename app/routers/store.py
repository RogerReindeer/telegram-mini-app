"""Authenticated Reader Coins wallet and store endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..schemas_commerce import StorePurchaseRequest, TestCoinGrantRequest
from ..services.auth import invalidate_access_cache, viewer_from_request
from ..services.coins import (
    CoinGrantTemporaryError,
    StoreInsufficientBalance,
    StoreProductAlreadyOwned,
    StoreProductNotFound,
    StorePurchaseConflict,
    StoreTemporaryError,
    StoreValidationError,
    get_wallet,
    grant_test_coins,
    list_store_products,
    list_user_entitlements,
    list_user_purchases,
    purchase_store_product,
)

router = APIRouter(prefix="/api/store", tags=["reader-coins"])


def _require_store_user(request: Request) -> tuple[dict, int]:
    viewer = viewer_from_request(request)
    if viewer.get("admin_preview"):
        raise HTTPException(status_code=403, detail="admin_preview_is_read_only")
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        raise HTTPException(status_code=401, detail="Откройте приложение внутри Telegram")
    return viewer, int(viewer["user_id"])


def _require_enabled() -> None:
    if not settings.reader_coins_enabled:
        raise HTTPException(status_code=404, detail="reader_coins_disabled")


@router.get("/wallet")
def wallet(request: Request):
    _require_enabled()
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


@router.get("/products")
def products(request: Request, novel_id: int | None = None, chapter_id: str | None = None):
    _require_enabled()
    viewer = viewer_from_request(request)
    if not viewer.get("authenticated") or (not viewer.get("user_id") and not viewer.get("admin_preview")):
        raise HTTPException(status_code=401, detail="Откройте приложение внутри Telegram")
    try:
        items = list_store_products(active_only=True, novel_id=novel_id, chapter_id=chapter_id)
    except Exception as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error
    return {
        "status": "ok",
        "currency": "reader_coins",
        "exchange_rate_rub": 1,
        "purchases_enabled": settings.reader_test_purchases_enabled and not viewer.get("admin_preview"),
        "test_topup_enabled": settings.reader_test_free_coins_enabled and not viewer.get("admin_preview"),
        "test_topup_min": max(10, settings.reader_test_coin_min_amount),
        "test_topup_max": min(100000, max(10, settings.reader_test_coin_max_amount)),
        "topup_url": settings.qinghe_shop_url or None,
        "items": items,
    }


@router.post("/test-coins")
def test_coins(request: Request, model: TestCoinGrantRequest):
    _require_enabled()
    if not settings.reader_test_free_coins_enabled:
        raise HTTPException(status_code=404, detail="test_coin_topup_disabled")
    _, user_id = _require_store_user(request)
    minimum = max(10, settings.reader_test_coin_min_amount)
    maximum = min(100000, max(minimum, settings.reader_test_coin_max_amount))
    if model.amount < minimum or model.amount > maximum:
        raise HTTPException(status_code=400, detail=f"amount_must_be_between_{minimum}_and_{maximum}")
    try:
        return grant_test_coins(user_id, model.amount, model.client_action_id)
    except StoreValidationError as error:
        raise HTTPException(status_code=400, detail="invalid_test_coin_amount") from error
    except StorePurchaseConflict as error:
        raise HTTPException(status_code=409, detail="test_coin_action_conflict") from error
    except StoreTemporaryError as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error


@router.post("/purchase")
def purchase(request: Request, model: StorePurchaseRequest):
    _require_enabled()
    if not settings.reader_test_purchases_enabled:
        raise HTTPException(status_code=404, detail="test_purchases_disabled")
    _, user_id = _require_store_user(request)
    try:
        result = purchase_store_product(user_id, model.product_code, model.client_action_id)
    except StoreProductNotFound as error:
        raise HTTPException(status_code=404, detail="store_product_not_found") from error
    except StoreInsufficientBalance as error:
        raise HTTPException(status_code=409, detail="insufficient_reader_coins") from error
    except StoreProductAlreadyOwned as error:
        raise HTTPException(status_code=409, detail="store_product_already_owned") from error
    except StorePurchaseConflict as error:
        raise HTTPException(status_code=409, detail="purchase_action_conflict") from error
    except StoreValidationError as error:
        raise HTTPException(status_code=400, detail="invalid_store_purchase") from error
    except StoreTemporaryError as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error
    invalidate_access_cache(user_id)
    return result


@router.get("/purchases")
def purchases(request: Request, limit: int = 100):
    _require_enabled()
    _, user_id = _require_store_user(request)
    try:
        return {"status": "ok", "items": list_user_purchases(user_id, limit=limit)}
    except Exception as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error


@router.get("/entitlements")
def entitlements(request: Request):
    _require_enabled()
    _, user_id = _require_store_user(request)
    try:
        return {"status": "ok", "items": list_user_entitlements(user_id)}
    except Exception as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error
