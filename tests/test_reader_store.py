from __future__ import annotations

from pathlib import Path
import re
from uuid import uuid4

import pytest
from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError

from app.database import SupabaseError
from app.schemas_commerce import (
    BulkNovelPricingPayload,
    SelectedChapterPricingPayload,
    StoreProductAdminPayload,
    TestCoinGrantRequest as CoinGrantRequest,
)
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


def test_bulk_pricing_schema_uses_requested_example_prices():
    model = BulkNovelPricingPayload(
        novel_ids="1-3",
        chapter_coin_price=5,
        bundle_coin_price=530,
    )
    assert model.chapter_coin_price == 5
    assert model.bundle_coin_price == 530


def test_selected_chapter_pricing_schema_normalizes_and_validates_modes():
    model = SelectedChapterPricingPayload(
        chapter_ids=[" 1-1 ", "1-1", "1-2"],
        coin_price=9,
    )
    assert model.chapter_ids == ["1-1", "1-2"]
    assert model.coin_price == 9
    reset = SelectedChapterPricingPayload(
        chapter_ids=["1-1"],
        coin_price=None,
        reset_to_default=True,
    )
    assert reset.reset_to_default is True
    with pytest.raises(ValidationError):
        SelectedChapterPricingPayload(chapter_ids=["1-1"], coin_price=None)
    with pytest.raises(ValidationError):
        SelectedChapterPricingPayload(
            chapter_ids=["1-1"],
            coin_price=5,
            reset_to_default=True,
        )


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ("1-3", [1, 2, 3]),
        ("1,3,5", [1, 3, 5]),
        ("1-3, 3, 5", [1, 2, 3, 5]),
        ("5; 7–8", [5, 7, 8]),
    ],
)
def test_parse_novel_id_selector_supports_ranges_and_lists(selector, expected):
    assert coins.parse_novel_id_selector(selector) == expected


@pytest.mark.parametrize("selector", ["", "0", "3-1", "abc", "1-101"])
def test_parse_novel_id_selector_rejects_invalid_or_oversized_values(selector):
    with pytest.raises(coins.StoreValidationError):
        coins.parse_novel_id_selector(selector)


def test_bulk_pricing_calls_atomic_rpc_with_normalized_ids(monkeypatch):
    captured = {}

    def fake_rpc(name, payload):
        captured.update({"name": name, "payload": payload})
        return [{"novels_updated": 3, "chapters_priced": 42, "bundles_priced": 3}]

    monkeypatch.setattr(coins, "db_rpc", fake_rpc)
    result = coins.set_bulk_novel_pricing("1-3", 5, 530)
    assert captured == {
        "name": "reader_set_bulk_novel_pricing",
        "payload": {
            "p_novel_ids": [1, 2, 3],
            "p_chapter_coin_price": 5,
            "p_bundle_coin_price": 530,
        },
    }
    assert result["chapters_priced"] == 42


def test_selected_chapter_pricing_calls_atomic_rpc(monkeypatch):
    captured = {}

    def fake_rpc(name, payload):
        captured.update({"name": name, "payload": payload})
        return [{"chapters_priced": 2, "novels_affected": 1, "overrides_reset": False}]

    monkeypatch.setattr(coins, "db_rpc", fake_rpc)
    result = coins.set_selected_chapter_prices(["1-1", "1-1", "1-2"], 9)
    assert captured == {
        "name": "reader_set_selected_chapter_prices",
        "payload": {
            "p_chapter_ids": ["1-1", "1-2"],
            "p_coin_price": 9,
            "p_reset_to_default": False,
        },
    }
    assert result["chapters_priced"] == 2


def test_visual_pricing_catalog_includes_titles_and_effective_prices(monkeypatch):
    tables = {
        "novels": [
            {"novel_id": 1, "code": "alpha", "novel_short": "Альфа", "miniapp_visible": True},
        ],
        "chapters": [
            {"chapter_id": "1-1", "novel_id": 1, "chapter_no": 1, "source_chapter_no": "1", "part_no": None, "chapter_title": "Начало"},
            {"chapter_id": "1-2", "novel_id": 1, "chapter_no": 2, "source_chapter_no": "2", "part_no": None, "chapter_title": "Продолжение"},
        ],
        coins.PRODUCT_TABLE: [
            {"product_type": "chapter_unlock", "novel_id": 1, "chapter_id": "1-1", "coin_price": 5, "is_active": True},
            {"product_type": "chapter_unlock", "novel_id": 1, "chapter_id": "1-2", "coin_price": 9, "is_active": True},
            {"product_type": "novel_unlock", "novel_id": 1, "chapter_id": None, "coin_price": 530, "is_active": True},
        ],
        coins.PRICING_RULE_TABLE: [
            {"novel_id": 1, "chapter_coin_price": 5, "bundle_coin_price": 530, "is_active": True},
        ],
        coins.CHAPTER_OVERRIDE_TABLE: [
            {"chapter_id": "1-2", "coin_price": 9},
        ],
    }
    monkeypatch.setattr(coins, "db_select", lambda table, **_kwargs: tables[table])
    catalog = coins.list_store_pricing_catalog()
    assert catalog["novels"][0]["title"] == "Альфа"
    assert catalog["novels"][0]["chapter_count"] == 2
    assert catalog["novels"][0]["bundle_coin_price"] == 530
    assert catalog["chapters"][0]["title"] == "Глава 1 — Начало"
    assert catalog["chapters"][0]["has_override"] is False
    assert catalog["chapters"][1]["override_coin_price"] == 9
    assert catalog["chapters"][1]["effective_coin_price"] == 9


def test_context_product_list_includes_chapter_bundle_and_subscriptions(monkeypatch):
    monkeypatch.setattr(coins, "db_select", lambda *_args, **_kwargs: [
        {"product_code": "chapter", "product_type": "chapter_unlock", "title": "Глава", "coin_price": 10, "novel_id": 5, "chapter_id": "5-1", "is_active": True},
        {"product_code": "other", "product_type": "chapter_unlock", "title": "Другая", "coin_price": 10, "novel_id": 5, "chapter_id": "5-2", "is_active": True},
        {"product_code": "book", "product_type": "novel_unlock", "title": "Книга", "coin_price": 100, "novel_id": 5, "is_active": True},
        {"product_code": "subscription", "product_type": "subscription", "title": "Подписка", "coin_price": 50, "subscription_role": "traveler", "duration_days": 30, "is_active": True},
    ])
    items = coins.list_store_products(novel_id=5, chapter_id="5-1")
    assert {item["product_code"] for item in items} == {"chapter", "book", "subscription"}


def test_novel_chapter_price_map_loads_only_active_chapter_products(monkeypatch):
    captured = {}

    def fake_select(table, **kwargs):
        captured.update({"table": table, **kwargs})
        return [
            {"chapter_id": "5-1", "coin_price": 5},
            {"chapter_id": "5-2", "coin_price": 9},
        ]

    monkeypatch.setattr(coins, "db_select", fake_select)
    assert coins.get_novel_chapter_price_map(5) == {"5-1": 5, "5-2": 9}
    assert captured["table"] == coins.PRODUCT_TABLE
    assert captured["filters"] == {
        "novel_id": "eq.5",
        "product_type": "eq.chapter_unlock",
        "is_active": "eq.true",
    }


def test_novel_chapter_price_map_fails_closed_on_database_outage(monkeypatch):
    monkeypatch.setattr(
        coins,
        "db_select",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SupabaseError("prices unavailable")),
    )
    with pytest.raises(coins.StoreTemporaryError, match="prices unavailable"):
        coins.get_novel_chapter_price_map(5)


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


def test_reader_store_ui_is_chapter_only_and_uses_transaction_modal():
    library = (ROOT / "templates" / "library.html").read_text(encoding="utf-8")
    chapter = (ROOT / "templates" / "chapter.html").read_text(encoding="utf-8")
    novel = (ROOT / "templates" / "novel.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "reader-store.js").read_text(encoding="utf-8")
    assert "data-reader-store" not in library
    assert "reader-store.js" not in library
    assert "data-reader-store" not in novel
    assert "reader-store.js" not in novel
    assert "chapter-coin-price" in novel
    assert 'data-chapter-id="{{ chapter.chapter_id }}"' in chapter
    assert "data-reader-transaction" in chapter
    assert "data-reader-coins-balance" in chapter
    assert "Подтверждение покупки" in script
    assert "Купить всю новеллу" in script
    assert "window.confirm" not in script


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
