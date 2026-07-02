"""Central configuration contract for new modules.

The legacy application currently reads the same environment variables directly.
New modules must import ``settings`` from here instead of reading ``os.environ``.
"""

from dataclasses import dataclass
import os
import re
from pathlib import Path

from dotenv import load_dotenv

SITE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(SITE_ROOT / ".env")


def normalize_telegram_chat_id(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"[\s\u00a0_,]", "", text)
    if not text:
        return ""
    if text.startswith("-100") and text[4:].isdigit():
        return text
    if text.startswith("-") and text[1:].isdigit():
        return text
    if text.isdigit():
        return f"-100{text}"
    return text


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str = _env("APP_ENV", "production").lower()
    supabase_url: str = _env("SUPABASE_URL").rstrip("/")
    supabase_service_key: str = _env("SUPABASE_SERVICE_KEY") or _env("SUPABASE_KEY")
    telegram_bot_token: str = _env("TELEGRAM_BOT_TOKEN")
    sync_token: str = _env("SYNC_TOKEN")
    session_secret: str = _env("SESSION_SECRET")
    traveler_chat_id: str = _env("TRAVELER_CHAT_ID")
    keeper_chat_id: str = _env("KEEPER_CHAT_ID")
    auth_session_ttl_seconds: int = int(_env("AUTH_SESSION_TTL_SECONDS", "900") or "900")
    telegram_init_data_max_age_seconds: int = int(_env("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS", "86400") or "86400")
    membership_cache_seconds: int = int(_env("MEMBERSHIP_CACHE_SECONDS", "300") or "300")
    tribute_api_key: str = _env("TRIBUTE_API_KEY")
    tribute_traveler_subscription_id: str = _env("TRIBUTE_TRAVELER_SUBSCRIPTION_ID")
    tribute_keeper_subscription_id: str = _env("TRIBUTE_KEEPER_SUBSCRIPTION_ID")
    tribute_traveler_url: str = _env("TRIBUTE_TRAVELER_URL")
    tribute_keeper_url: str = _env("TRIBUTE_KEEPER_URL")
    access_debug_enabled: bool = _env("ACCESS_DEBUG_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    catalog_cache_seconds: int = int(_env("CATALOG_CACHE_SECONDS", "60") or "60")
    telegraph_cache_seconds: int = int(_env("TELEGRAPH_CACHE_SECONDS", "1800") or "1800")
    image_cache_seconds: int = int(_env("IMAGE_CACHE_SECONDS", "1800") or "1800")

    rate_limit_enabled: bool = _env("RATE_LIMIT_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    rate_limit_window_seconds: int = int(_env("RATE_LIMIT_WINDOW_SECONDS", "60") or "60")
    rate_limit_public_max_requests: int = int(_env("RATE_LIMIT_PUBLIC_MAX_REQUESTS", "240") or "240")
    rate_limit_sensitive_max_requests: int = int(_env("RATE_LIMIT_SENSITIVE_MAX_REQUESTS", "60") or "60")
    static_cache_seconds: int = int(_env("STATIC_CACHE_SECONDS", "86400") or "86400")
    app_version: str = _env("APP_VERSION", "v134-reader-settings-infinite-scroll")
    app_events_enabled: bool = _env("APP_EVENTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    app_metrics_enabled: bool = _env("APP_METRICS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

    @property
    def normalized_traveler_chat_id(self) -> str:
        return normalize_telegram_chat_id(self.traveler_chat_id)

    @property
    def normalized_keeper_chat_id(self) -> str:
        return normalize_telegram_chat_id(self.keeper_chat_id)

    def validate_production(self) -> list[str]:
        missing: list[str] = []
        for field_name in (
            "supabase_url",
            "supabase_service_key",
            "telegram_bot_token",
            "sync_token",
            "session_secret",
        ):
            if not getattr(self, field_name):
                missing.append(field_name.upper())
        return missing


settings = Settings()
