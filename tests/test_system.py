from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.routers import system


ROOT = Path(__file__).resolve().parents[1]


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


def test_startup_shell_is_minimal_and_wakes_backend():
    response = system.startup_shell()
    shell = Path(response.path).read_text(encoding="utf-8")
    assert response.media_type == "text/html"
    assert '<button class="loader-shell"' in shell
    assert '<span class="spinner"' in shell
    assert "Открываем библиотеку" not in shell
    assert "Зефиркины баоцзы" not in shell
    assert "telegram-mini-app-fwq0.onrender.com" in shell
    assert "/health" in shell
    assert "Render" not in shell
    assert '<meta name="robots" content="noindex, nofollow, noarchive">' in shell
    assert response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"


def test_startup_worker_only_shows_shell_for_same_page_reload():
    response = system.startup_worker()
    worker = Path(response.path).read_text(encoding="utf-8")
    settings_script = (ROOT / "static" / "settings.js").read_text(encoding="utf-8")
    assert response.headers["service-worker-allowed"] == "/"
    assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert 'request.mode !== "navigate"' in worker
    assert 'url.pathname.startsWith("/chapter/")' in worker
    assert "self.clients.get(event.clientId)" in worker
    assert "requested.pathname === current.pathname" in worker
    assert "if (!(await isReloadOfCurrentPage(event))) return fetch(event.request);" in worker
    assert "__reader_boot" in worker
    assert 'navigator.serviceWorker.register("/startup-sw.js"' in settings_script
    assert 'url.searchParams.delete("__reader_boot")' in settings_script


def test_root_render_blueprint_includes_always_on_static_launcher():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "name: telegram-mini-app-launcher" in blueprint
    assert "runtime: static" in blueprint
    assert "rootDir: launcher" in blueprint
    assert "staticPublishPath: ." in blueprint
    assert "destination: /index.html" in blueprint
    assert "name: Content-Security-Policy" in blueprint
    assert "name: X-Robots-Tag" in blueprint
