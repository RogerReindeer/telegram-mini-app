"""Reader Coins wallet service.

Qinghe owns the purchase. The reader owns only the resulting Reader Coins balance
and immutable ledger. Cross-database transfer happens through the signed internal
HTTP endpoint; Qinghe never receives Reader Supabase credentials.
"""

from __future__ import annotations

from typing import Any

from ..database import SupabaseError, db_rpc, db_select, supabase_ready

WALLET_TABLE = "reader_coin_wallets"
LEDGER_TABLE = "reader_coin_ledger"
CREDIT_RPC = "reader_credit_coins_from_qinghe"


class CoinGrantConflict(RuntimeError):
    pass


class CoinGrantTemporaryError(RuntimeError):
    pass


def get_wallet(telegram_user_id: int) -> dict[str, Any]:
    user_id = int(telegram_user_id or 0)
    if user_id <= 0:
        return {"telegram_user_id": None, "balance": 0, "lifetime_credited": 0, "lifetime_spent": 0}
    if not supabase_ready():
        raise CoinGrantTemporaryError("Supabase is not configured")
    rows = db_select(
        WALLET_TABLE,
        select="telegram_user_id,balance,lifetime_credited,lifetime_spent,updated_at",
        filters={"telegram_user_id": f"eq.{user_id}"},
        limit=1,
    )
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

    row: dict[str, Any]
    if isinstance(result, list) and result and isinstance(result[0], dict):
        row = result[0]
    elif isinstance(result, dict):
        row = result
    else:
        raise CoinGrantTemporaryError("Unexpected Reader Coins RPC response")

    return {
        "status": "completed",
        "event_id": str(payload["event_id"]),
        "purchase_id": str(payload["purchase_id"]),
        "credited": int(row.get("credited") or 0),
        "balance": int(row.get("balance") or 0),
        "duplicate": bool(row.get("duplicate")),
    }
