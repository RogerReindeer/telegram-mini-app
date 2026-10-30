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
    FinishTestCommerceRequest,
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


def test_finish_test_requires_exact_confirmation_phrase():
    assert FinishTestCommerceRequest(
        confirmation="FINISH_READER_COMMERCE_TEST"
    ).confirmation == "FINISH_READER_COMMERCE_TEST"
    with pytest.raises(ValidationError):
        FinishTestCommerceRequest(confirmation="finish")


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


def test_purchase_history_has_titles_and_hides_test_rollbacks(monkeypatch):
    def fake_select(table, **_kwargs):
        if table == coins.PURCHASE_TABLE:
            return [
                {"id": "purchase-1", "product_code": "chapter:5-1", "coin_price": 5, "status": "completed", "purchased_at": "2026-10-29T10:00:00Z", "reversed_at": None},
                {"id": "purchase-2", "product_code": "chapter:5-2", "coin_price": 5, "status": "reversed", "purchased_at": "2026-10-29T11:00:00Z", "reversed_at": "2026-10-29T12:00:00Z"},
            ]
        if table == coins.PRODUCT_TABLE:
            return [
                {"product_code": "chapter:5-1", "product_type": "chapter_unlock", "title": "Глава 1"},
                {"product_code": "chapter:5-2", "product_type": "chapter_unlock", "title": "Глава 2"},
            ]
        return []

    monkeypatch.setattr(coins, "db_select", fake_select)
    history = coins.list_user_purchases(42)
    assert history == [{
        "id": "purchase-1",
        "product_code": "chapter:5-1",
        "product_type": "chapter_unlock",
        "title": "Глава 1",
        "coin_price": 5,
        "purchased_at": "2026-10-29T10:00:00Z",
    }]


def test_purchase_maps_insufficient_balance(monkeypatch):
    monkeypatch.setattr(coins, "db_rpc", lambda *_args, **_kwargs: (_ for _ in ()).throw(SupabaseError("reader_insufficient_balance")))
    with pytest.raises(coins.StoreInsufficientBalance):
        coins.purchase_store_product(42, "chapter", uuid4(), test_mode=True)


def test_store_runtime_settings_are_server_controlled(monkeypatch):
    monkeypatch.setattr(coins, "db_select", lambda *_args, **_kwargs: [{
        "test_mode_enabled": False,
        "stars_coins_per_star": 1,
        "stars_min_coin_amount": 10,
        "updated_at": "2026-10-30T00:00:00Z",
    }])
    runtime = coins.get_store_runtime_settings()
    assert runtime["test_mode_enabled"] is False
    assert runtime["stars_coins_per_star"] == 1
    assert runtime["stars_min_coin_amount"] == 10


def test_finish_test_calls_single_atomic_rpc(monkeypatch):
    captured = {}

    def fake_rpc(name, payload):
        captured.update({"name": name, "payload": payload})
        return [{
            "reset_wallets": 2,
            "cleared_coins": 120,
            "reversed_purchases": 3,
            "revoked_entitlements": 3,
        }]

    monkeypatch.setattr(coins, "db_rpc", fake_rpc)
    result = coins.finish_test_commerce("FINISH_READER_COMMERCE_TEST")
    assert captured == {
        "name": "reader_finish_test_commerce",
        "payload": {"p_confirmation": "FINISH_READER_COMMERCE_TEST"},
    }
    assert result["test_mode_enabled"] is False
    assert result["cleared_coins"] == 120


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


def test_reader_store_ui_uses_chapter_and_subscription_transaction_modals():
    library = (ROOT / "templates" / "library.html").read_text(encoding="utf-8")
    chapter = (ROOT / "templates" / "chapter.html").read_text(encoding="utf-8")
    novel = (ROOT / "templates" / "novel.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "reader-store.js").read_text(encoding="utf-8")
    store_router = (ROOT / "app" / "routers" / "store.py").read_text(encoding="utf-8")
    settings_script = (ROOT / "static" / "settings-panel.js").read_text(encoding="utf-8")
    transaction = (ROOT / "templates" / "_reader_transaction_modal.html").read_text(encoding="utf-8")
    assert "data-reader-store" not in library
    assert "reader-store.js" not in library
    assert 'data-store-mode="subscription"' in novel
    assert "novel-subscription-toc-blur" in novel
    assert "reader-store.js" in novel
    assert "chapter-coin-price" in novel
    assert 'data-chapter-id="{{ chapter.chapter_id }}"' in chapter
    assert '_reader_transaction_modal.html' in chapter
    assert "data-reader-transaction" in transaction
    assert "data-reader-coins-balance" in transaction
    assert "[10, 50, 100, 250, 500, 1000]" in transaction
    assert 'data-reader-stars-topup-amount="{{ amount }}"' in transaction
    assert "data-reader-stars-custom" in transaction
    assert "Купить через Tribute в @qinghe_rpg_bot" in transaction
    assert "1 ⭐ = 1 Монетка" in transaction
    assert 'url.searchParams.set("provider", "telegram_stars")' not in script
    assert "Переход в Qinghe доступен только для Tribute" in script
    assert "!state.starsTopupEnabled" in script
    assert 'TRIBUTE_BOT_URL = "https://t.me/qinghe_rpg_bot"' in store_router
    assert '"stars_topup_enabled": False' in store_router
    assert "Подтверждение покупки" in script
    assert "Купить всю новеллу" in script
    assert "Все текущие и будущие главы без срока" in script
    assert 'state.mode === "subscription"' in script
    assert "state.suggestedTopup" in script
    assert "data-zb-purchase-history" in settings_script
    assert "История покупок" in settings_script
    assert "window.confirm" not in script


def test_admin_has_guarded_finish_test_action():
    template = (ROOT / "templates" / "admin.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "admin-store.js").read_text(encoding="utf-8")
    assert "data-admin-store-finish-test" in template
    assert "История операций сохраняется" in template
    assert "ЗАВЕРШИТЬ ТЕСТ" in script
    assert "FINISH_READER_COMMERCE_TEST" in script


def test_tribute_copy_is_limited_to_the_qinghe_topup_redirect():
    searchable = [ROOT / "app", ROOT / "templates", ROOT / "static", ROOT / ".env.example"]
    matches = []
    for base in searchable:
        paths = [base] if base.is_file() else list(base.rglob("*"))
        for path in paths:
            if path.is_file() and path.suffix.lower() in {".py", ".html", ".js", ".css", ".example"}:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
                if re.search(r"\btribute\b", text):
                    matches.append(str(path.relative_to(ROOT)))
    assert set(matches) == {
        "app\\routers\\store.py",
        "static\\reader-store.js",
        "templates\\_reader_transaction_modal.html",
    }


def test_global_mouse_wheel_scroll_has_root_contract_and_runtime_fallback():
    settings_script = (ROOT / "static" / "settings.js").read_text(encoding="utf-8")
    enhancements = (ROOT / "static" / "enhancements.css").read_text(encoding="utf-8")
    assert "initReliableWheelScrolling();" in settings_script
    assert 'document.addEventListener("wheel"' in settings_script
    assert "document.scrollingElement || root" in settings_script
    assert 'root.classList.toggle("reader-scroll-locked", isScrollLocked())' in settings_script
    assert "new MutationObserver(syncRootScrollLock)" in settings_script
    assert '{ passive: true }' in settings_script
    assert "overflow-x: clip !important" in enhancements
    assert "html.reader-scroll-locked" in enhancements
    assert "body:not(.reader-transaction-open):not(.zb-settings-open):not(.reader-quick-settings-open)" in enhancements
    assert "overflow-y: visible !important" in enhancements


def test_library_discovery_has_grouped_filters_dynamic_tags_and_fuzzy_search():
    library = (ROOT / "templates" / "library.html").read_text(encoding="utf-8")
    settings_script = (ROOT / "static" / "settings.js").read_text(encoding="utf-8")
    enhancements = (ROOT / "static" / "enhancements.css").read_text(encoding="utf-8")
    assert 'data-filter-group="reading"' in library
    assert 'data-filter-group="project"' in library
    assert 'data-filter-group="access"' in library
    assert 'id="libraryDynamicTagChips"' in library
    assert 'id="libraryResultSummary"' in library
    assert 'id="libraryEmptyReset"' in library
    assert "buildLibraryDynamicTags()" in settings_script
    assert "normalizeLibrarySearchText" in settings_script
    assert "boundedLibraryDistance" in settings_script
    assert "grouped[group].some" in settings_script
    assert "updateLibraryFilterFacetCounts" in settings_script
    assert "subscription_access" in settings_script
    assert "library-filter-open" in settings_script
    assert "v244 — thoughtful library discovery" in enhancements
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in enhancements
