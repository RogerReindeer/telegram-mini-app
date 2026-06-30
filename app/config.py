from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_TITLE = os.getenv("APP_TITLE", "Зефиркины баоцзы")
APP_VERSION = os.getenv("APP_VERSION", "v110-mobile-reader-stable")


def _clean(value: str | None) -> str:
    return (value or "").strip()


@dataclass(frozen=True)
class Settings:
    app_title: str = APP_TITLE
    app_version: str = APP_VERSION
    app_env: str = os.getenv("APP_ENV", "production")
    supabase_url: str = _clean(os.getenv("SUPABASE_URL"))
    supabase_key: str = _clean(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))
    sync_token: str = _clean(os.getenv("SYNC_TOKEN"))
    session_secret: str = _clean(os.getenv("SESSION_SECRET", "change-me"))
    telegram_bot_token: str = _clean(os.getenv("TELEGRAM_BOT_TOKEN"))
    traveler_chat_id: str = _clean(os.getenv("TRAVELER_CHAT_ID"))
    keeper_chat_id: str = _clean(os.getenv("KEEPER_CHAT_ID"))
    boosty_traveler_url: str = _clean(os.getenv("BOOSTY_TRAVELER_URL") or os.getenv("BOOSTY_ACCESS_URL") or "https://boosty.to/")
    static_cache_seconds: int = int(os.getenv("STATIC_CACHE_SECONDS", "3600"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    rate_limit_max_requests: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "180"))

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def telegram_bot_configured(self) -> bool:
        return bool(self.telegram_bot_token)


settings = Settings()
