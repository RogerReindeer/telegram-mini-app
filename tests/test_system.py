from __future__ import annotations

import json
from types import SimpleNamespace

from app.routers import system


def ready_settings(missing: list[str]):
    return SimpleNamespace(
        validate_production=lambda: missing,
        reader_coins_enabled=False,
        reader_coin_grants_enabled=False,
        app_version="test",
    )


def test_ready_is_503_when_required_configuration_is_missing(monkeypatch):
    monkeypatch.setattr(system, "settings", ready_settings(["SYNC_TOKEN"]))
    monkeypatch.setattr(system, "supabase_ready", lambda: False)
    response = system.ready()
    payload = json.loads(response.body)
    assert response.status_code == 503
    assert payload["status"] == "degraded"
    assert payload["missing"] == ["SYNC_TOKEN"]


def test_ready_is_200_when_configuration_is_complete(monkeypatch):
    monkeypatch.setattr(system, "settings", ready_settings([]))
    monkeypatch.setattr(system, "supabase_ready", lambda: True)
    monkeypatch.setattr(system, "db_select", lambda *args, **kwargs: [])
    response = system.ready()
    assert response.status_code == 200


def test_ready_is_503_when_database_round_trip_fails(monkeypatch):
    monkeypatch.setattr(system, "settings", ready_settings([]))
    monkeypatch.setattr(system, "supabase_ready", lambda: True)
    monkeypatch.setattr(system, "db_select", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    response = system.ready()
    assert response.status_code == 503
