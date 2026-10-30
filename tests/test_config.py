from __future__ import annotations

from app.config import _app_version, _reader_coins_feature_enabled


def test_explicit_app_version_wins(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "release-42")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    assert _app_version() == "release-42"


def test_render_commit_drives_default_version(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    assert _app_version() == "git-abcdef123456"


def test_test_purchase_mode_automatically_enables_reader_coins_ui(monkeypatch):
    monkeypatch.setenv("READER_COINS_ENABLED", "false")
    monkeypatch.setenv("READER_COIN_GRANTS_ENABLED", "false")
    monkeypatch.setenv("READER_TEST_FREE_COINS_ENABLED", "true")
    monkeypatch.setenv("READER_TEST_PURCHASES_ENABLED", "true")
    assert _reader_coins_feature_enabled() is True


def test_reader_coins_ui_stays_disabled_when_every_mode_is_off(monkeypatch):
    for name in (
        "READER_COINS_ENABLED",
        "READER_COIN_GRANTS_ENABLED",
        "READER_STORE_PURCHASES_ENABLED",
        "READER_TEST_FREE_COINS_ENABLED",
        "READER_TEST_PURCHASES_ENABLED",
    ):
        monkeypatch.setenv(name, "false")
    assert _reader_coins_feature_enabled() is False


def test_production_store_mode_automatically_enables_reader_coins_ui(monkeypatch):
    monkeypatch.setenv("READER_COINS_ENABLED", "false")
    monkeypatch.setenv("READER_STORE_PURCHASES_ENABLED", "true")
    monkeypatch.setenv("READER_COIN_GRANTS_ENABLED", "false")
    monkeypatch.setenv("READER_TEST_FREE_COINS_ENABLED", "false")
    monkeypatch.setenv("READER_TEST_PURCHASES_ENABLED", "false")
    assert _reader_coins_feature_enabled() is True
