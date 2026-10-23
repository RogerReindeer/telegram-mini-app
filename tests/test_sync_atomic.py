from __future__ import annotations

import inspect

from app.services import sync


def test_run_sync_is_synchronous_for_threadpool_boundary():
    assert not inspect.iscoroutinefunction(sync.run_sync)


def test_atomic_snapshot_uses_single_rpc_and_strips_private_keys(monkeypatch):
    calls = []

    def fake_rpc(name, payload):
        calls.append((name, payload))
        return {
            "novels_upserted": 1,
            "chapters_upserted": 1,
            "fox_upserted": 1,
            "stale_chapters_deleted": 2,
            "stale_novels_deleted": 3,
            "stale_fox_deleted": 4,
        }

    monkeypatch.setattr(sync, "db_rpc", fake_rpc)
    result = sync._apply_atomic_catalog_snapshot(
        [{"novel_id": 1, "__row_number": 8}],
        [{"chapter_id": "1-1", "__sheet_name": "Chapters"}],
        [{"name": "fox", "url": "https://example.test/fox.png"}],
    )
    assert len(calls) == 1
    assert calls[0][0] == "apply_catalog_snapshot"
    assert calls[0][1]["p_novels"] == [{"novel_id": 1}]
    assert result["stale_novels_deleted"] == 3
