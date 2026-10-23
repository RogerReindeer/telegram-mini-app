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
