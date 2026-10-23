from __future__ import annotations

from app.config import _app_version


def test_explicit_app_version_wins(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "release-42")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    assert _app_version() == "release-42"


def test_render_commit_drives_default_version(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    assert _app_version() == "git-abcdef123456"
