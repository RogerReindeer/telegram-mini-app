from __future__ import annotations

from types import SimpleNamespace

from app.services import production


def test_content_check_warns_when_successful_sync_is_stale(monkeypatch):
    monkeypatch.setattr(production, "settings", SimpleNamespace(sync_stale_after_hours=48))
    audit = {
        "counts": {
            "errors": 0,
            "warnings": 0,
            "novels": 1,
            "visible_novels": 1,
            "chapters": 1,
        },
        "latest_sync_runs": [{
            "status": "ok",
            "finished_at": "2000-01-01T00:00:00+00:00",
        }],
    }

    checks = production._content_checks(audit)
    freshness = next(item for item in checks if item["name"] == "content.sync_freshness")

    assert freshness["status"] == "warn"
    assert freshness["details"]["age_hours"] > 48
