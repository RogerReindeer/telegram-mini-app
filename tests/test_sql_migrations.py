from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_current_schema_adds_legacy_boosty_columns_before_foreign_keys():
    sql = (ROOT / "sql" / "migrations" / "001_current_schema.sql").read_text(encoding="utf-8")
    add_column = sql.index(
        "alter table public.boosty_products add column if not exists novel_id bigint;"
    )
    foreign_key = sql.index(
        "foreign key (novel_id) references public.novels(novel_id) on delete set null;"
    )
    assert add_column < foreign_key


def test_current_schema_converts_legacy_boosty_primary_keys():
    sql = (ROOT / "sql" / "migrations" / "001_current_schema.sql").read_text(encoding="utf-8")
    assert "primary key (boosty_bundle_key)" in sql
    assert "primary key (boosty_order_id)" in sql
    assert "user_entitlements_source_uidx" in sql


def test_reader_coins_migrates_legacy_ledger_before_event_index():
    sql = (ROOT / "sql" / "migrations" / "003_reader_coins.sql").read_text(encoding="utf-8")
    rename_event = sql.index("rename column source_event_id to event_id")
    event_index = sql.index("on public.reader_coin_ledger(event_id) where event_id is not null;")
    assert rename_event < event_index
    assert "rename column ledger_id to id" in sql
    assert "rename column operation to operation_type" in sql
    assert "rename column source_purchase_id to purchase_id" in sql


def test_reader_coins_relaxes_legacy_insert_blockers():
    sql = (ROOT / "sql" / "migrations" / "003_reader_coins.sql").read_text(encoding="utf-8")
    assert "alter column balance_before drop not null" in sql
    assert "drop constraint if exists reader_coin_ledger_operation" in sql
    assert "drop constraint if exists reader_coin_ledger_amount_positive" in sql
    assert "reader_coin_ledger_idempotency_key_idx" in sql


def test_reader_store_purchase_and_rollback_are_atomic_service_role_rpcs():
    sql = (ROOT / "sql" / "migrations" / "005_reader_store_test_commerce.sql").read_text(encoding="utf-8")
    assert "create or replace function public.reader_grant_test_coins" in sql
    assert "create or replace function public.reader_purchase_product" in sql
    assert "create or replace function public.reader_rollback_test_purchases" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "reader_insufficient_balance" in sql
    assert "reader_product_already_owned" in sql
    assert "set revoked_at = now()" in sql
    assert "operation_type in ('qinghe_grant', 'store_spend')" in sql
    assert "revoke execute on function public.reader_purchase_product" in sql
    assert "grant execute on function public.reader_purchase_product" in sql


def test_bulk_novel_pricing_persists_rules_and_prices_future_chapters():
    sql = (ROOT / "sql" / "migrations" / "006_reader_bulk_novel_pricing.sql").read_text(
        encoding="utf-8"
    )
    assert "create table if not exists public.reader_novel_pricing_rules" in sql
    assert "create or replace function public.reader_set_bulk_novel_pricing" in sql
    assert "reader_chapters_apply_pricing_rule" in sql
    assert "after insert or update of novel_id, chapter_title, title" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "reader_store_products_active_chapter_target_idx" in sql
    assert "reader_store_products_active_novel_target_idx" in sql
    assert "alter table public.reader_novel_pricing_rules enable row level security" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql


def test_visual_pricing_editor_preserves_per_chapter_overrides():
    sql = (ROOT / "sql" / "migrations" / "007_reader_visual_pricing_editor.sql").read_text(
        encoding="utf-8"
    )
    assert "create table if not exists public.reader_chapter_pricing_overrides" in sql
    assert "create or replace function public.reader_set_selected_chapter_prices" in sql
    assert "coalesce(price_override.coin_price, p_chapter_coin_price)" in sql
    assert "reader_missing_novel_pricing_rule" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "alter table public.reader_chapter_pricing_overrides enable row level security" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql


def test_stars_rate_and_test_finish_are_atomic_and_service_role_only():
    sql = (ROOT / "sql" / "migrations" / "008_reader_stars_and_test_finish.sql").read_text(
        encoding="utf-8"
    )
    assert "create table if not exists public.reader_store_runtime_settings" in sql
    assert "stars_coins_per_star integer not null default 1" in sql
    assert "stars_min_coin_amount integer not null default 10" in sql
    assert "create or replace function public.reader_finish_test_commerce" in sql
    assert "create or replace function public.reader_purchase_product_v2" in sql
    assert "create or replace function public.reader_grant_test_coins_v2" in sql
    assert "FINISH_READER_COMMERCE_TEST" in sql
    assert "reader_real_commerce_present" in sql
    assert "pg_advisory_xact_lock_shared" in sql
    assert "set test_mode_enabled = false" in sql
    assert "set balance = 0" in sql
    assert "lifetime_credited = 0" in sql
    assert "set revoked_at = now()" in sql
    assert "coalesce(entitlement.metadata ->> 'test_mode', 'false') = 'true'" in sql
    assert "security invoker" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql


def test_security_hardening_removes_duplicate_analytics_trigger_before_rebuild():
    sql = (ROOT / "sql" / "migrations" / "004_security_analytics_hardening.sql").read_text(
        encoding="utf-8"
    )
    drop_trigger = sql.index("drop trigger if exists analytics_events_touch_user_profile")
    rebuild = sql.index("with event_rollup as")
    assert drop_trigger < rebuild
    assert "drop function if exists public.analytics_touch_user_profile();" in sql
    assert "alter view public.analytics_daily set (security_invoker = true);" in sql


def test_security_hardening_closes_public_access_and_adds_keys_and_indexes():
    sql = (ROOT / "sql" / "migrations" / "004_security_analytics_hardening.sql").read_text(
        encoding="utf-8"
    )
    assert "enable row level security" in sql
    assert "from public, anon, authenticated" in sql
    assert "primary key (subscription_id)" in sql
    assert "primary key (entitlement_id)" in sql
    assert "user_chapter_progress_chapter_idx" in sql
    assert "user_novel_state_novel_fk_idx" in sql
