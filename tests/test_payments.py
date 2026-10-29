from __future__ import annotations

import pytest
from app.services import payments


def test_boosty_order_id_cannot_be_reassigned_to_another_user(monkeypatch):
    monkeypatch.setattr(
        payments,
        "db_select",
        lambda table, **_kwargs: [{
            "boosty_order_id": "order-1",
            "boosty_bundle_key": "book-1",
            "telegram_user_id": 100,
        }] if table == "boosty_orders" else [],
    )

    with pytest.raises(payments.PaymentConflictError):
        payments.import_boosty_order({
            "boosty_order_id": "order-1",
            "boosty_bundle_key": "book-1",
            "telegram_user_id": 200,
        })
