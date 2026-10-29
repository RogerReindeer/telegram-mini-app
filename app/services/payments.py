"""Payment and paid-access service.

This module owns inbound payment/provider flows. Page handlers and routers should
not write payment tables directly: they call this service and receive a small
result object that is safe to return from API routes.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..database import db_select, db_upsert
from .auth import clean_value, invalidate_access_cache, to_int, utc_now


class PaymentPayloadError(ValueError):
    """Raised when a provider payload is incomplete or malformed."""


class PaymentProductNotFoundError(LookupError):
    """Raised when an imported order references an unknown product."""


class PaymentConflictError(RuntimeError):
    """Raised when an external order id is reused for different data."""


def import_boosty_order(payload: dict[str, Any]) -> dict[str, Any]:
    order_key = clean_value(payload.get("boosty_order_id"))
    product_key = clean_value(payload.get("boosty_bundle_key"))
    telegram_user_id = to_int(payload.get("telegram_user_id"), 0)

    if not order_key or not product_key or not telegram_user_id:
        raise PaymentPayloadError("Нужны boosty_order_id, boosty_bundle_key и telegram_user_id")

    existing_orders = db_select(
        "boosty_orders",
        select="boosty_order_id,boosty_bundle_key,telegram_user_id",
        filters={"boosty_order_id": f"eq.{quote(order_key, safe='')}"},
        limit=1,
    )
    if existing_orders:
        existing = existing_orders[0]
        existing_user_id = to_int(existing.get("telegram_user_id"), 0)
        existing_product_key = clean_value(existing.get("boosty_bundle_key"))
        if existing_user_id and existing_user_id != telegram_user_id:
            raise PaymentConflictError("Этот boosty_order_id уже привязан к другому пользователю")
        if existing_product_key and existing_product_key != product_key:
            raise PaymentConflictError("Этот boosty_order_id уже привязан к другому продукту")

    products = db_select(
        "boosty_products",
        filters={"boosty_bundle_key": f"eq.{quote(product_key, safe='')}"},
        limit=1,
    )
    if not products:
        raise PaymentProductNotFoundError("Бандл не зарегистрирован в boosty_products")

    product = products[0]
    novel_id = to_int(product.get("novel_id"), 0)
    if novel_id <= 0:
        raise PaymentPayloadError("У Boosty-бандла не задан корректный novel_id")
    now_iso = utc_now().isoformat()
    order_row = {
        "boosty_order_id": order_key,
        "boosty_bundle_key": product_key,
        "buyer_email": clean_value(payload.get("buyer_email")) or None,
        "buyer_name": clean_value(payload.get("buyer_name")) or None,
        "amount": payload.get("amount"),
        "currency": clean_value(payload.get("currency")) or None,
        "payment_status": "paid",
        "purchased_at": clean_value(payload.get("purchased_at")) or now_iso,
        "telegram_user_id": telegram_user_id,
        "claimed_at": now_iso,
        "raw_email": payload,
    }
    db_upsert("boosty_orders", [order_row], "boosty_order_id", batch_size=1)

    entitlement = {
        "telegram_user_id": telegram_user_id,
        "novel_id": novel_id,
        "source_type": "boosty_bundle",
        "source_id": order_key,
        "access_type": product.get("access_type") or "full_book",
        "granted_at": now_iso,
        "metadata": {
            "boosty_bundle_key": product_key,
            "product_name": product.get("product_name"),
        },
    }
    db_upsert(
        "user_entitlements",
        [entitlement],
        "telegram_user_id,novel_id,source_type,source_id",
        batch_size=1,
    )
    invalidate_access_cache(telegram_user_id)

    return {
        "status": "ok",
        "telegram_user_id": telegram_user_id,
        "novel_id": novel_id,
    }
