from __future__ import annotations

from pathlib import Path
import re
from uuid import uuid4

import pytest
from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError

from app.database import SupabaseError
from app.schemas_commerce import StoreProductAdminPayload, TestCoinGrantRequest as CoinGrantRequest
from app.services import coins


ROOT = Path(__file__).resolve().parents[1]


def test_test_coin_grant_enforces_minimum():
    with pytest.raises(ValidationError):
        CoinGrantRequest(amount=9, client_action_id=uuid4())
    assert CoinGrantRequest(amount=10, client_action_id=uuid4()).amount == 10


def test_store_product_shape_matches_target_type():
    chapter = StoreProductAdminPayload(
        product_type="chapter_unlock",
        title="Глава 12",
        coin_price=25,
        novel_id=501,
        chapter_id="501-12",
    )
    assert chapter.chapter_id == "501-12"
    with pytest.raises(ValidationError):
        StoreProductAdminPayload(
            product_type="subscription",
            title="Keeper",
            coin_price=300,
            novel_id=501,
            subscription_role="keeper",
            duration_days=30,
        )


def test_context_product_list_includes_chapter_bundle_and_subscriptions(monkeypatch):
    monkeypatch.setattr(coins, "db_select", lambda *_args, **_kwargs: [
        {"product_code": "chapter", "product_type": "chapter_unlock", "title": "Глава", "coin_price": 10, "novel_id": 5, "chapter_id": "5-1", "is_active": True},
        {"product_code": "other", "product_type": "chapter_unlock", "title": "Другая", "coin_price": 10, "novel_id": 5, "chapter_id": "5-2", "is_active": True},
        {"product_code": "book", "product_type": "novel_unlock", "title": "Книга", "coin_price": 100, "novel_id": 5, "is_active": True},
        {"product_code": "subscription", "product_type": "subscription", "title": "Подписка", "coin_price": 50, "subscription_role": "traveler", "duration_days": 30, "is_active": True},
    ])
    items = coins.list_store_products(novel_id=5, chapter_id="5-1")
    assert {item["product_code"] for item in items} == {"chapter", "book", "subscription"}


def test_purchase_maps_insufficient_balance(monkeypatch):
    monkeypatch.setattr(coins, "db_rpc", lambda *_args, **_kwargs: (_ for _ in ()).throw(SupabaseError("reader_insufficient_balance")))
    with pytest.raises(coins.StoreInsufficientBalance):
        coins.purchase_store_product(42, "chapter", uuid4())


def test_wallet_maps_database_outage(monkeypatch):
    monkeypatch.setattr(coins, "supabase_ready", lambda: True)
    monkeypatch.setattr(
        coins,
        "db_select",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SupabaseError("wallet unavailable")),
    )
    with pytest.raises(coins.CoinGrantTemporaryError, match="wallet unavailable"):
        coins.get_wallet(42)


def test_admin_rejects_chapter_bound_to_another_novel(monkeypatch):
    monkeypatch.setattr(
        coins,
        "db_select",
        lambda table, **_kwargs: [{"chapter_id": "5-1", "novel_id": 6}] if table == "chapters" else [],
    )
    with pytest.raises(coins.StoreValidationError, match="не принадлежит"):
        coins.upsert_store_product("chapter-5-1", {
            "product_type": "chapter_unlock",
            "title": "Глава 1",
            "coin_price": 25,
            "novel_id": 5,
            "chapter_id": "5-1",
        })


def test_admin_rejects_unknown_novel(monkeypatch):
    monkeypatch.setattr(coins, "db_select", lambda *_args, **_kwargs: [])
    with pytest.raises(coins.StoreValidationError, match="Новелла не найдена"):
        coins.upsert_store_product("novel-999", {
            "product_type": "novel_unlock",
            "title": "Книга",
            "coin_price": 250,
            "novel_id": 999,
        })


def test_admin_maps_product_target_lookup_outage(monkeypatch):
    monkeypatch.setattr(
        coins,
        "db_select",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SupabaseError("database unavailable")),
    )
    with pytest.raises(coins.StoreTemporaryError, match="database unavailable"):
        coins.upsert_store_product("novel-5", {
            "product_type": "novel_unlock",
            "title": "Книга",
            "coin_price": 250,
            "novel_id": 5,
        })


def test_admin_maps_product_reload_outage(monkeypatch):
    monkeypatch.setattr(coins, "db_upsert", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        coins,
        "db_select",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SupabaseError("product reload unavailable")),
    )
    with pytest.raises(coins.StoreTemporaryError, match="product reload unavailable"):
        coins.upsert_store_product("keeper-30", {
            "product_type": "subscription",
            "title": "Хранитель на 30 дней",
            "coin_price": 300,
            "subscription_role": "keeper",
            "duration_days": 30,
        })


def test_all_templates_compile_after_store_ui_changes():
    environment = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
    for path in (ROOT / "templates").glob("*.html"):
        environment.get_template(path.name)


def test_reader_has_no_removed_payment_provider_route_or_ui_copy():
    searchable = [ROOT / "app", ROOT / "templates", ROOT / "static", ROOT / ".env.example"]
    matches = []
    for base in searchable:
        paths = [base] if base.is_file() else list(base.rglob("*"))
        for path in paths:
            if path.is_file() and path.suffix.lower() in {".py", ".html", ".js", ".css", ".example"}:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
                if re.search(r"\btribute\b", text):
                    matches.append(str(path.relative_to(ROOT)))
    assert matches == []
