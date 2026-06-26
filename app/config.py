"""Central configuration contract for new modules.

The legacy application currently reads the same environment variables directly.
New modules must import ``settings`` from here instead of reading ``os.environ``.
"""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

SITE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(SITE_ROOT / ".env")


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
