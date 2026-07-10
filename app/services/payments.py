"""Payment and paid-access service.

This module owns inbound payment/provider flows. Page handlers and routers should
not write payment tables directly: they call this service and receive a small
result object that is safe to return from API routes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any
from urllib.parse import quote

from ..config import settings
from ..database import db_select, db_update, db_upsert
from .auth import clean_value, invalidate_access_cache, to_int, utc_now

TRIBUTE_SUBSCRIPTION_EVENTS = {
    "new_subscription",
    "renewed_subscription",
    "cancelled_subscription",
}


def payment_event_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def tribute_signature_valid(raw_body: bytes, signature: str) -> bool:
    if not settings.tribute_api_key or not signature:
        return False

    signature = signature.strip()
    if signature.lower().startswith("sha256="):
        signature = signature.split("=", 1)[1]

    digest = hmac.new(
        settings.tribute_api_key.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).digest()

    return hmac.compare_digest(signature.lower(), digest.hex().lower()) or hmac.compare_digest(
        signature,
        base64.b64encode(digest).decode("ascii"),
    )


def tribute_access_role(subscription_id: Any) -> str | None:
    value = clean_value(subscription_id)
    if value and value == settings.tribute_keeper_subscription_id:
        return "keeper"
    if value and value == settings.tribute_traveler_subscription_id:
        return "traveler"
    return None


def record_payment_event(
    provider: str,
    event_hash: str,
    event_name: str,
    payload: dict[str, Any],
    status: str,
    error: str | None = None,
) -> None:
    event_payload = payload.get("payload") or {}
    row = {
        "provider": provider,
        "event_hash": event_hash,
        "event_name": event_name,
        "telegram_user_id": to_int(event_payload.get("telegram_user_id"), 0) or None,
        "external_plan_id": clean_value(event_payload.get("subscription_id")) or None,
        "payload": payload,
        "status": status,
        "error_message": error,
        "processed_at": utc_now().isoformat() if status in {"processed", "ignored", "error"} else None,
    }

    try:
        db_upsert("payment_events", [row], "provider,event_hash", batch_size=1)
    except Exception as exc:
        # Webhook delivery should not fail only because the audit log failed.
        print("Unable to record payment event:", exc)


def upsert_tribute_subscription(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    telegram_user_id = to_int(payload.get("telegram_user_id"), 0)
    subscription_id = clean_value(payload.get("subscription_id"))
    role = tribute_access_role(subscription_id)

    if not telegram_user_id or not subscription_id:
        raise ValueError("В webhook отсутствуют telegram_user_id или subscription_id")

    if not role:
        return {
            "status": "ignored",
            "reason": "unknown_subscription",
            "subscription_id": subscription_id,
        }

    cancelled = event_name == "cancelled_subscription"
    now_iso = utc_now().isoformat()
    row = {
        "telegram_user_id": telegram_user_id,
        "provider": "tribute",
        "external_plan_id": subscription_id,
        "access_role": role,
        "status": "cancelling" if cancelled else "active",
        "subscription_type": clean_value(payload.get("type")) or None,
        "auto_renew": not cancelled,
        "started_at": clean_value(payload.get("purchase_created_at") or payload.get("created_at")) or None,
        "expires_at": clean_value(payload.get("expires_at")) or now_iso,
        "cancelled_at": now_iso if cancelled else None,
        "renewed_at": now_iso if event_name == "renewed_subscription" else None,
        "telegram_username": clean_value(payload.get("telegram_username")) or None,
        "provider_user_id": clean_value(payload.get("trb_user_id")) or None,
    }

    db_upsert(
        "user_subscriptions",
        [row],
        "telegram_user_id,provider,external_plan_id",
        batch_size=1,
    )
    invalidate_access_cache(telegram_user_id)

    return {"status": "processed", "role": role, "telegram_user_id": telegram_user_id}


def decode_tribute_event(raw_body: bytes) -> dict[str, Any]:
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Некорректный JSON Tribute") from exc

    if not isinstance(event, dict):
        raise ValueError("Webhook Tribute должен быть JSON-объектом")

    return event


def process_tribute_webhook(raw_body: bytes, signature: str) -> dict[str, Any]:
    if not tribute_signature_valid(raw_body, signature):
        raise PermissionError("Неверная подпись Tribute")

    event = decode_tribute_event(raw_body)
    event_name = clean_value(event.get("name"))
    payload = event.get("payload") or {}
    event_hash = payment_event_hash(raw_body)

    if event_name not in TRIBUTE_SUBSCRIPTION_EVENTS:
        record_payment_event("tribute", event_hash, event_name, event, "ignored")
        return {"status": "ok", "result": "ignored"}

    try:
        result = upsert_tribute_subscription(event_name, payload)
        record_payment_event("tribute", event_hash, event_name, event, result.get("status", "processed"))
        return {"status": "ok", "result": result}
    except Exception as error:
        record_payment_event("tribute", event_hash, event_name, event, "error", str(error))
        raise


def import_boosty_order(payload: dict[str, Any]) -> dict[str, Any]:
    order_key = clean_value(payload.get("boosty_order_id"))
    product_key = clean_value(payload.get("boosty_bundle_key"))
    telegram_user_id = to_int(payload.get("telegram_user_id"), 0)

    if not order_key or not product_key or not telegram_user_id:
        raise ValueError("Нужны boosty_order_id, boosty_bundle_key и telegram_user_id")

    products = db_select(
        "boosty_products",
        filters={"boosty_bundle_key": f"eq.{quote(product_key, safe='')}"},
        limit=1,
    )
    if not products:
        raise LookupError("Бандл не зарегистрирован в boosty_products")

    product = products[0]
    now_iso = utc_now().isoformat()

    existing_orders = db_select(
        "boosty_orders",
        filters={"boosty_order_id": f"eq.{quote(order_key, safe='')}"},
        limit=1,
    )
    previous_owner_id = to_int(existing_orders[0].get("telegram_user_id"), 0) if existing_orders else 0

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
        "novel_id": product["novel_id"],
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

    if previous_owner_id and previous_owner_id != telegram_user_id:
        # The conflict key above includes telegram_user_id, so re-importing
        # the same boosty_order_id under a different account (CRM correction
        # or operator mistake) would otherwise ADD a second entitlement row
        # instead of moving it, leaving both accounts with access to a
        # single purchase. Revoke the previous owner's entitlement for this
        # exact order instead.
        db_update(
            "user_entitlements",
            {
                "telegram_user_id": f"eq.{previous_owner_id}",
                "novel_id": f"eq.{product['novel_id']}",
                "source_type": "eq.boosty_bundle",
                "source_id": f"eq.{quote(order_key, safe='')}",
            },
            {"revoked_at": now_iso},
        )
        invalidate_access_cache(previous_owner_id)

    return {
        "status": "ok",
        "telegram_user_id": telegram_user_id,
        "novel_id": product["novel_id"],
    }
