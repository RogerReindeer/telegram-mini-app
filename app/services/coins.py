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
PRICING_RULE_TABLE = "reader_novel_pricing_rules"
CHAPTER_OVERRIDE_TABLE = "reader_chapter_pricing_overrides"
RUNTIME_SETTINGS_TABLE = "reader_store_runtime_settings"
CREDIT_RPC = "reader_credit_coins_from_qinghe"
TEST_CREDIT_RPC = "reader_grant_test_coins_v2"
PURCHASE_RPC = "reader_purchase_product_v2"
ROLLBACK_RPC = "reader_rollback_test_purchases"
FINISH_TEST_RPC = "reader_finish_test_commerce"
BULK_PRICING_RPC = "reader_set_bulk_novel_pricing"
SELECTED_CHAPTER_PRICING_RPC = "reader_set_selected_chapter_prices"
MAX_BULK_PRICING_NOVELS = 100


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


def get_store_runtime_settings() -> dict[str, Any]:
    """Load the server-only commerce switch and fail closed on outages.

    The database switch lets an administrator end the test atomically without
    waiting for a Render redeploy. Environment flags remain the outer gate.
    """
    try:
        rows = db_select(
            RUNTIME_SETTINGS_TABLE,
            select="test_mode_enabled,stars_coins_per_star,stars_min_coin_amount,updated_at",
            filters={"id": "eq.1"},
            limit=1,
        )
    except SupabaseError as error:
        raise StoreTemporaryError(str(error)) from error
    if not rows:
        raise StoreTemporaryError("Reader store runtime settings are missing")
    row = rows[0]
    return {
        "test_mode_enabled": bool(row.get("test_mode_enabled")),
        "stars_coins_per_star": max(1, int(row.get("stars_coins_per_star") or 1)),
        "stars_min_coin_amount": max(10, int(row.get("stars_min_coin_amount") or 10)),
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


def get_novel_chapter_price_map(novel_id: int) -> dict[str, int]:
    """Return active per-chapter prices for one novel's table of contents."""
    target_novel_id = int(novel_id or 0)
    if target_novel_id <= 0:
        return {}
    try:
        rows = db_select(
            PRODUCT_TABLE,
            select="chapter_id,coin_price",
            filters={
                "novel_id": f"eq.{target_novel_id}",
                "product_type": "eq.chapter_unlock",
                "is_active": "eq.true",
            },
            order="chapter_id.asc",
        )
    except SupabaseError as error:
        raise StoreTemporaryError(str(error)) from error
    return {
        str(row.get("chapter_id") or ""): int(row.get("coin_price") or 0)
        for row in rows
        if row.get("chapter_id") and int(row.get("coin_price") or 0) > 0
    }


def purchase_store_product(
    telegram_user_id: int,
    product_code: str,
    client_action_id: Any,
    *,
    test_mode: bool,
) -> dict[str, Any]:
    try:
        row = _rpc_row(db_rpc(PURCHASE_RPC, {
            "p_telegram_user_id": int(telegram_user_id),
            "p_product_code": str(product_code).strip(),
            "p_client_action_id": str(client_action_id),
            "p_test_mode": bool(test_mode),
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
    rows = db_select(
        PURCHASE_TABLE,
        select="id,product_code,coin_price,status,purchased_at,reversed_at",
        filters={"telegram_user_id": f"eq.{int(telegram_user_id)}"},
        order="purchased_at.desc",
        limit=max(1, min(int(limit), 250)),
    )
    products = db_select(
        PRODUCT_TABLE,
        select="product_code,product_type,title",
        order="product_code.asc",
    )
    products_by_code = {
        str(product.get("product_code") or ""): product
        for product in products
        if product.get("product_code")
    }
    result: list[dict[str, Any]] = []
    for row in rows:
        # Test rollbacks remain an administrator tool and are not presented as
        # a user-facing refund flow. The history shows completed purchases only.
        if str(row.get("status") or "") != "completed" or row.get("reversed_at"):
            continue
        product = products_by_code.get(str(row.get("product_code") or ""), {})
        result.append({
            "id": str(row.get("id") or ""),
            "product_code": str(row.get("product_code") or ""),
            "product_type": str(product.get("product_type") or ""),
            "title": str(product.get("title") or row.get("product_code") or "Покупка"),
            "coin_price": int(row.get("coin_price") or 0),
            "purchased_at": row.get("purchased_at"),
        })
    return result


def list_user_entitlements(telegram_user_id: int) -> list[dict[str, Any]]:
    return db_select(
        ENTITLEMENT_TABLE,
        select="id,purchase_id,entitlement_type,novel_id,chapter_id,subscription_role,starts_at,expires_at,revoked_at,created_at",
        filters={"telegram_user_id": f"eq.{int(telegram_user_id)}"},
        order="created_at.desc",
    )


def parse_novel_id_selector(value: Any) -> list[int]:
    text = str(value or "").strip()
    if not text:
        raise StoreValidationError("Укажите ID новелл")
    text = text.replace("–", "-").replace("—", "-").replace(";", ",").replace("\n", ",")
    result: set[int] = set()
    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            pieces = [piece.strip() for piece in part.split("-")]
            if len(pieces) != 2 or not all(piece.isdigit() for piece in pieces):
                raise StoreValidationError(f"Некорректный диапазон ID: {part}")
            start, end = (int(piece) for piece in pieces)
            if start <= 0 or end < start:
                raise StoreValidationError(f"Некорректный диапазон ID: {part}")
            if end - start + 1 > MAX_BULK_PRICING_NOVELS:
                raise StoreValidationError("Один диапазон не может содержать больше 100 новелл")
            result.update(range(start, end + 1))
        else:
            if not part.isdigit() or int(part) <= 0:
                raise StoreValidationError(f"Некорректный ID новеллы: {part}")
            result.add(int(part))
        if len(result) > MAX_BULK_PRICING_NOVELS:
            raise StoreValidationError("За один раз можно настроить не больше 100 новелл")
    if not result:
        raise StoreValidationError("Укажите ID новелл")
    return sorted(result)


def list_novel_pricing_rules() -> list[dict[str, Any]]:
    try:
        rows = db_select(PRICING_RULE_TABLE, order="novel_id.asc")
    except SupabaseError as error:
        raise StoreTemporaryError(str(error)) from error
    return [
        {
            "novel_id": int(row.get("novel_id") or 0),
            "chapter_coin_price": int(row.get("chapter_coin_price") or 0),
            "bundle_coin_price": int(row.get("bundle_coin_price") or 0),
            "is_active": bool(row.get("is_active")),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]


def _catalog_text(value: Any) -> str:
    return str(value or "").strip()


def list_store_pricing_catalog() -> dict[str, Any]:
    """Return an admin-only visual pricing catalog with effective prices."""
    try:
        novels = db_select(
            "novels",
            select="novel_id,code,novel_short,title_ru,miniapp_visible",
            order="novel_id.asc",
        )
        chapters = db_select(
            "chapters",
            select=(
                "chapter_id,novel_id,volume_no,volume_title,chapter_no,"
                "source_chapter_no,part_no,chapter_title"
            ),
            order="novel_id.asc,chapter_no.asc,part_no.asc,chapter_id.asc",
        )
        products = db_select(
            PRODUCT_TABLE,
            select="product_type,novel_id,chapter_id,coin_price,is_active",
            filters={"is_active": "eq.true"},
            order="product_code.asc",
        )
        rules = db_select(PRICING_RULE_TABLE, order="novel_id.asc")
        overrides = db_select(CHAPTER_OVERRIDE_TABLE, order="chapter_id.asc")
    except SupabaseError as error:
        raise StoreTemporaryError(str(error)) from error

    rules_by_novel = {
        int(row["novel_id"]): row
        for row in rules
        if row.get("novel_id") is not None and bool(row.get("is_active"))
    }
    overrides_by_chapter = {
        _catalog_text(row.get("chapter_id")): int(row.get("coin_price") or 0)
        for row in overrides
        if _catalog_text(row.get("chapter_id"))
    }
    chapter_prices: dict[str, int] = {}
    bundle_prices: dict[int, int] = {}
    for row in products:
        product_type = _catalog_text(row.get("product_type"))
        if product_type == "chapter_unlock" and row.get("chapter_id") is not None:
            chapter_prices[_catalog_text(row.get("chapter_id"))] = int(row.get("coin_price") or 0)
        elif product_type == "novel_unlock" and row.get("novel_id") is not None:
            bundle_prices[int(row["novel_id"])] = int(row.get("coin_price") or 0)

    chapter_count_by_novel: dict[int, int] = {}
    chapter_items: list[dict[str, Any]] = []
    for row in chapters:
        chapter_id = _catalog_text(row.get("chapter_id"))
        novel_id = int(row.get("novel_id") or 0)
        if not chapter_id or novel_id <= 0:
            continue
        chapter_count_by_novel[novel_id] = chapter_count_by_novel.get(novel_id, 0) + 1
        rule = rules_by_novel.get(novel_id)
        default_price = int(rule.get("chapter_coin_price") or 0) if rule else None
        override_price = overrides_by_chapter.get(chapter_id)
        effective_price = chapter_prices.get(chapter_id)
        source_number = _catalog_text(row.get("source_chapter_no")) or _catalog_text(row.get("chapter_no"))
        part_number = _catalog_text(row.get("part_no"))
        number_label = source_number or chapter_id
        chapter_title = _catalog_text(row.get("chapter_title"))
        if chapter_title.casefold().startswith("глава"):
            label = chapter_title
        else:
            label = f"Глава {number_label}"
            if part_number and part_number != "0":
                label += f", часть {part_number}"
            if chapter_title:
                label += f" — {chapter_title}"
        chapter_items.append({
            "chapter_id": chapter_id,
            "novel_id": novel_id,
            "title": label,
            "chapter_title": chapter_title or None,
            "chapter_no": row.get("chapter_no"),
            "source_chapter_no": row.get("source_chapter_no"),
            "part_no": row.get("part_no"),
            "effective_coin_price": effective_price,
            "default_coin_price": default_price,
            "override_coin_price": override_price,
            "has_override": override_price is not None,
            "is_priced": effective_price is not None,
        })

    novel_items: list[dict[str, Any]] = []
    for row in novels:
        novel_id = int(row.get("novel_id") or 0)
        if novel_id <= 0:
            continue
        rule = rules_by_novel.get(novel_id)
        title = (
            _catalog_text(row.get("novel_short"))
            or _catalog_text(row.get("title_ru"))
            or _catalog_text(row.get("code"))
            or f"Новелла {novel_id}"
        )
        novel_items.append({
            "novel_id": novel_id,
            "title": title,
            "code": _catalog_text(row.get("code")) or None,
            "is_visible": row.get("miniapp_visible") is not False,
            "chapter_count": chapter_count_by_novel.get(novel_id, 0),
            "chapter_coin_price": int(rule.get("chapter_coin_price") or 0) if rule else None,
            "bundle_coin_price": bundle_prices.get(
                novel_id,
                int(rule.get("bundle_coin_price") or 0) if rule else None,
            ),
            "has_pricing_rule": rule is not None,
        })

    return {
        "status": "ok",
        "exchange_rate_rub": 1,
        "novels": novel_items,
        "chapters": chapter_items,
    }


def set_bulk_novel_pricing(
    novel_selector: Any,
    chapter_coin_price: int,
    bundle_coin_price: int,
) -> dict[str, Any]:
    novel_ids = parse_novel_id_selector(novel_selector)
    try:
        row = _rpc_row(db_rpc(BULK_PRICING_RPC, {
            "p_novel_ids": novel_ids,
            "p_chapter_coin_price": int(chapter_coin_price),
            "p_bundle_coin_price": int(bundle_coin_price),
        }), operation="bulk novel pricing")
    except SupabaseError as error:
        message = str(error)
        if "reader_invalid_bulk_pricing" in message:
            raise StoreValidationError("Некорректные параметры массовых цен") from error
        if "reader_unknown_novel_ids" in message:
            missing = message.split("reader_unknown_novel_ids:", 1)[-1].split('"', 1)[0]
            raise StoreValidationError(f"Новеллы не найдены: {missing}") from error
        raise StoreTemporaryError(message) from error
    return {
        "status": "ok",
        "novel_ids": novel_ids,
        "chapter_coin_price": int(chapter_coin_price),
        "bundle_coin_price": int(bundle_coin_price),
        "novels_updated": int(row.get("novels_updated") or 0),
        "chapters_priced": int(row.get("chapters_priced") or 0),
        "bundles_priced": int(row.get("bundles_priced") or 0),
    }


def set_selected_chapter_prices(
    chapter_ids: list[str],
    coin_price: int | None,
    *,
    reset_to_default: bool = False,
) -> dict[str, Any]:
    normalized = list(dict.fromkeys(str(value).strip() for value in chapter_ids if str(value).strip()))
    if not normalized or len(normalized) > 500:
        raise StoreValidationError("Выберите от 1 до 500 глав")
    try:
        row = _rpc_row(db_rpc(SELECTED_CHAPTER_PRICING_RPC, {
            "p_chapter_ids": normalized,
            "p_coin_price": None if reset_to_default else int(coin_price or 0),
            "p_reset_to_default": bool(reset_to_default),
        }), operation="selected chapter pricing")
    except SupabaseError as error:
        message = str(error)
        if "reader_unknown_chapter_ids" in message:
            missing = message.split("reader_unknown_chapter_ids:", 1)[-1].split('"', 1)[0]
            raise StoreValidationError(f"Главы не найдены: {missing}") from error
        if "reader_missing_novel_pricing_rule" in message:
            raise StoreValidationError(
                "Сначала задайте общую цену главы для выбранной новеллы"
            ) from error
        if "reader_invalid_selected_chapter_pricing" in message:
            raise StoreValidationError("Некорректные параметры цен глав") from error
        raise StoreTemporaryError(message) from error
    return {
        "status": "ok",
        "chapters_priced": int(row.get("chapters_priced") or 0),
        "novels_affected": int(row.get("novels_affected") or 0),
        "overrides_reset": bool(row.get("overrides_reset")),
    }


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
        if any(sqlstate in message for sqlstate in ("23503", "23505", "23514", "22P02")):
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


def finish_test_commerce(confirmation: str) -> dict[str, Any]:
    try:
        row = _rpc_row(
            db_rpc(FINISH_TEST_RPC, {"p_confirmation": str(confirmation)}),
            operation="finish test commerce",
        )
    except SupabaseError as error:
        message = str(error)
        if "reader_invalid_test_finish_confirmation" in message:
            raise StoreValidationError(message) from error
        if "reader_test_mode_already_finished" in message:
            raise StoreValidationError("Тестовый режим уже завершён") from error
        if "reader_real_commerce_present" in message:
            raise StoreValidationError(
                "В базе уже есть боевые операции: автоматический общий сброс заблокирован"
            ) from error
        raise StoreTemporaryError(message) from error
    return {
        "status": "completed",
        "test_mode_enabled": False,
        "reset_wallets": int(row.get("reset_wallets") or 0),
        "cleared_coins": int(row.get("cleared_coins") or 0),
        "reversed_purchases": int(row.get("reversed_purchases") or 0),
        "revoked_entitlements": int(row.get("revoked_entitlements") or 0),
    }
