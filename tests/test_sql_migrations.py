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
