from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_title: str = os.getenv('APP_TITLE', 'Зефиркины баоцзы')
    app_version: str = os.getenv('APP_VERSION', 'v111-mobile-library-cleanup')
    supabase_url: str = os.getenv('SUPABASE_URL', '').rstrip('/')
    supabase_key: str = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY') or ''
    sync_token: str = os.getenv('SYNC_TOKEN', '')
    telegram_channel_url: str = os.getenv('TELEGRAM_CHANNEL_URL', 'https://t.me/zefirkinybaozhy')

    @property
    def supabase_ready(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


settings = Settings()
