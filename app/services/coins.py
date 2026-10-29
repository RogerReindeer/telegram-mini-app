"""Server-only Reader Coins wallet and store service.

The browser never talks to the Reader Coins tables or RPCs directly. The
application authenticates the Telegram viewer, calls service-role-only
database functions, and returns only that viewer's data.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..database import SupabaseError, db_rpc, db_select, db_upsert, supabase_ready
from ..utils import utc_now

WALLET_TABLE = "reader_coin_wallets"
LEDGER_TABLE = "reader_coin_ledger"
PRODUCT_TABLE = "reader_store_products"
PURCHASE_TABLE = "reader_store_purchases"
ENTITLEMENT_TABLE = "reader_commerce_entitlements"
CREDIT_RPC = "reader_credit_coins_from_qinghe"
TEST_CREDIT_RPC = "reader_grant_test_coins"
PURCHASE_RPC = "reader_purchase_product"
ROLLBACK_RPC = "reader_rollback_test_purchases"


class CoinGrantConflict(RuntimeError):
    pass


class CoinGrantTemporaryError(RuntimeError):
    pass


class StoreProductNotFound(RuntimeError):
    pass


class StorePurchaseConflict(RuntimeError):
    pass


class StoreProductAlreadyOwned(RuntimeError):
    pass


class StoreInsufficientBalance(RuntimeError):
    pass


class StoreValidationError(RuntimeError):
    pass


class StoreTemporaryError(RuntimeError):
    pass


def _rpc_row(result: Any, *, operation: str) -> dict[str, Any]:
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return result[0]
    if isinstance(result, dict):
        return result
    raise StoreTemporaryError(f"Unexpected {operation} RPC response")


def get_wallet(telegram_user_id: int) -> dict[str, Any]:
    user_id = int(telegram_user_id or 0)
    if user_id <= 0:
        return {"telegram_user_id": None, "balance": 0, "lifetime_credited": 0, "lifetime_spent": 0}
    if not supabase_ready():
        raise CoinGrantTemporaryError("Supabase is not configured")
    try:
        rows = db_select(
            WALLET_TABLE,
            select="telegram_user_id,balance,lifetime_credited,lifetime_spent,updated_at",
            filters={"telegram_user_id": f"eq.{user_id}"},
            limit=1,
        )
    except SupabaseError as error:
        raise CoinGrantTemporaryError(str(error)) from error
    if not rows:
        return {"telegram_user_id": user_id, "balance": 0, "lifetime_credited": 0, "lifetime_spent": 0, "updated_at": None}
    row = rows[0]
    return {
        "telegram_user_id": user_id,
        "balance": int(row.get("balance") or 0),
        "lifetime_credited": int(row.get("lifetime_credited") or 0),
        "lifetime_spent": int(row.get("lifetime_spent") or 0),
        "updated_at": row.get("updated_at"),
    }


def credit_from_qinghe(payload: dict[str, Any]) -> dict[str, Any]:
    rpc_payload = {
        "p_event_id": str(payload["event_id"]),
        "p_purchase_id": str(payload["purchase_id"]),
        "p_telegram_user_id": int(payload["telegram_user_id"]),
        "p_product_code": str(payload["product_code"]),
        "p_amount": int(payload["amount"]),
        "p_provider": str(payload["provider"]),
        "p_occurred_at": payload["occurred_at"].isoformat() if hasattr(payload.get("occurred_at"), "isoformat") else str(payload["occurred_at"]),
    }
    try:
        result = db_rpc(CREDIT_RPC, rpc_payload)
    except SupabaseError as error:
        message = str(error)
        if "reader_purchase_conflict" in message or "reader_event_conflict" in message:
            raise CoinGrantConflict(message) from error
        raise CoinGrantTemporaryError(message) from error
    except Exception as error:
        raise CoinGrantTemporaryError(str(error)) from error

    try:
        row = _rpc_row(result, operation="Reader Coins")
    except StoreTemporaryError as error:
        raise CoinGrantTemporaryError(str(error)) from error

    return {
        "status": "completed",
        "event_id": str(payload["event_id"]),
        "purchase_id": str(payload["purchase_id"]),
        "credited": int(row.get("credited") or 0),
        "balance": int(row.get("balance") or 0),
        "duplicate": bool(row.get("duplicate")),
    }


def grant_test_coins(telegram_user_id: int, amount: int, client_action_id: Any) -> dict[str, Any]:
    try:
        row = _rpc_row(db_rpc(TEST_CREDIT_RPC, {
            "p_telegram_user_id": int(telegram_user_id),
            "p_amount": int(amount),
            "p_client_action_id": str(client_action_id),
        }), operation="test grant")
    except SupabaseError as error:
        message = str(error)
        if "reader_invalid_test_grant" in message:
            raise StoreValidationError(message) from error
        if "reader_test_grant_conflict" in message:
            raise StorePurchaseConflict(message) from error
        raise StoreTemporaryError(message) from error
    return {
        "status": "completed",
        "credited": int(row.get("credited") or 0),
        "balance": int(row.get("balance") or 0),
        "duplicate": bool(row.get("duplicate")),
    }


def _public_product(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_code": str(row.get("product_code") or ""),
        "product_type": str(row.get("product_type") or ""),
        "title": str(row.get("title") or ""),
        "coin_price": int(row.get("coin_price") or 0),
        "novel_id": int(row["novel_id"]) if row.get("novel_id") is not None else None,
        "chapter_id": str(row.get("chapter_id") or "") or None,
        "subscription_role": str(row.get("subscription_role") or "") or None,
        "duration_days": int(row["duration_days"]) if row.get("duration_days") is not None else None,
        "upgrade_from_role": str(row.get("upgrade_from_role") or "") or None,
        "is_active": bool(row.get("is_active")),
        "sort_order": int(row.get("sort_order") or 0),
    }


def list_store_products(
    *,
    active_only: bool = True,
    novel_id: int | None = None,
    chapter_id: str | None = None,
) -> list[dict[str, Any]]:
    filters = {"is_active": "eq.true"} if active_only else None
    rows = db_select(PRODUCT_TABLE, filters=filters, order="sort_order.asc,coin_price.asc,product_code.asc")
    products = [_public_product(row) for row in rows]
    if novel_id is None and not chapter_id:
        return products

    result: list[dict[str, Any]] = []
    for product in products:
        product_type = product["product_type"]
        if product_type in {"subscription", "subscription_upgrade"}:
            result.append(product)
        elif product_type == "novel_unlock" and novel_id and product["novel_id"] == novel_id:
            result.append(product)
        elif (
            product_type == "chapter_unlock"
            and chapter_id
            and product["chapter_id"] == chapter_id
            and (novel_id is None or product["novel_id"] == novel_id)
        ):
            result.append(product)
    return result


def purchase_store_product(telegram_user_id: int, product_code: str, client_action_id: Any) -> dict[str, Any]:
    try:
        row = _rpc_row(db_rpc(PURCHASE_RPC, {
            "p_telegram_user_id": int(telegram_user_id),
            "p_product_code": str(product_code).strip(),
            "p_client_action_id": str(client_action_id),
        }), operation="purchase")
    except SupabaseError as error:
        message = str(error)
        if "reader_product_not_found" in message:
            raise StoreProductNotFound(message) from error
        if "reader_insufficient_balance" in message:
            raise StoreInsufficientBalance(message) from error
        if "reader_product_already_owned" in message:
            raise StoreProductAlreadyOwned(message) from error
        if "reader_purchase_action_conflict" in message:
            raise StorePurchaseConflict(message) from error
        if "reader_invalid_purchase" in message or "reader_product_target_invalid" in message:
            raise StoreValidationError(message) from error
        raise StoreTemporaryError(message) from error
    return {
        "status": str(row.get("purchase_status") or "completed"),
        "purchase_id": str(row.get("purchase_id") or ""),
        "product_code": str(row.get("product_code") or product_code),
        "product_type": str(row.get("product_type") or ""),
        "spent": int(row.get("spent") or 0),
        "balance": int(row.get("balance") or 0),
        "duplicate": bool(row.get("duplicate")),
    }


def list_user_purchases(telegram_user_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
    return db_select(
        PURCHASE_TABLE,
        select="id,product_code,coin_price,status,purchased_at,reversed_at",
        filters={"telegram_user_id": f"eq.{int(telegram_user_id)}"},
        order="purchased_at.desc",
        limit=max(1, min(int(limit), 250)),
    )


def list_user_entitlements(telegram_user_id: int) -> list[dict[str, Any]]:
    return db_select(
        ENTITLEMENT_TABLE,
        select="id,purchase_id,entitlement_type,novel_id,chapter_id,subscription_role,starts_at,expires_at,revoked_at,created_at",
        filters={"telegram_user_id": f"eq.{int(telegram_user_id)}"},
        order="created_at.desc",
    )


def upsert_store_product(product_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    code = str(product_code or "").strip()
    if not code or len(code) > 120:
        raise StoreValidationError("Некорректный product_code")
    product_type = str(payload.get("product_type") or "")
    novel_id = payload.get("novel_id")
    chapter_id = payload.get("chapter_id")
    try:
        if product_type == "chapter_unlock":
            chapters = db_select(
                "chapters",
                select="chapter_id,novel_id",
                filters={"chapter_id": f"eq.{quote(str(chapter_id), safe='')}"},
                limit=1,
            )
            if not chapters or int(chapters[0].get("novel_id") or 0) != int(novel_id or 0):
                raise StoreValidationError("Глава не найдена или не принадлежит выбранной новелле")
        elif product_type == "novel_unlock":
            novels = db_select(
                "novels",
                select="novel_id",
                filters={"novel_id": f"eq.{int(novel_id or 0)}"},
                limit=1,
            )
            if not novels:
                raise StoreValidationError("Новелла не найдена")
    except SupabaseError as error:
        raise StoreTemporaryError(str(error)) from error

    row = {
        "product_code": code,
        "product_type": product_type,
        "title": str(payload["title"]).strip(),
        "coin_price": int(payload["coin_price"]),
        "novel_id": novel_id,
        "chapter_id": chapter_id,
        "subscription_role": payload.get("subscription_role"),
        "duration_days": payload.get("duration_days"),
        "upgrade_from_role": payload.get("upgrade_from_role"),
        "is_active": bool(payload.get("is_active", True)),
        "sort_order": int(payload.get("sort_order") or 0),
        "metadata": {"exchange_rate_rub": 1, "managed_by": "reader_admin"},
        "updated_at": utc_now().isoformat(),
    }
    try:
        db_upsert(PRODUCT_TABLE, [row], "product_code", batch_size=1)
        rows = db_select(PRODUCT_TABLE, filters={"product_code": f"eq.{quote(code, safe='')}"}, limit=1)
    except SupabaseError as error:
        message = str(error)
        if any(sqlstate in message for sqlstate in ("23503", "23514", "22P02")):
            raise StoreValidationError(message) from error
        raise StoreTemporaryError(message) from error
    if not rows:
        raise StoreTemporaryError("Product was not returned after upsert")
    return _public_product(rows[0])


def rollback_test_purchases(telegram_user_id: int | None = None) -> dict[str, Any]:
    try:
        row = _rpc_row(db_rpc(ROLLBACK_RPC, {"p_telegram_user_id": telegram_user_id}), operation="rollback")
    except SupabaseError as error:
        message = str(error)
        if "reader_invalid_rollback_user" in message:
            raise StoreValidationError(message) from error
        raise StoreTemporaryError(message) from error
    return {
        "status": "completed",
        "reversed_purchases": int(row.get("reversed_purchases") or 0),
        "refunded_coins": int(row.get("refunded_coins") or 0),
        "affected_users": int(row.get("affected_users") or 0),
    }
