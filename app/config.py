# Build history compatibility markers: v245-user-subscriptions-schema-compat; v244-teletype-mirror-media-recovery; v243-sync-media-repair; v242-reader-coins-foundation; v241-browser-reader-link; v240-production-gate-hardening; v239-miniapp-visible-direct-route; v238-admin-browser-preview; v204-single-miniapp-sync-source; v208-readable-chapter-title-center; v209-unified-corner-radius; v230-subscription-support-copy; v233-access-gate-copy; v234-gift-subscription-level-chooser; v235-gift-support-copy-channel-chooser; v236-role-aware-subscription-paywalls
# Build history compatibility markers: v229-group-subscriptions-reset-label; v226-persistent-analytics-personal-stats; v227-vertical-chapter-swipe; v228-settings-popup-selects-about-copy
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


def normalize_telegram_chat_ids(value: str, fallback: str = "") -> tuple[str, ...]:
    raw = str(value or fallback or "")
    parts = re.split(r"[;,\n]+", raw)
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        chat_id = normalize_telegram_chat_id(part)
        if not chat_id or chat_id in seen:
            continue
        seen.add(chat_id)
        result.append(chat_id)
    return tuple(result)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str = _env("APP_ENV", "production").lower()
    supabase_url: str = _env("SUPABASE_URL").rstrip("/")
    supabase_service_key: str = _env("SUPABASE_SERVICE_KEY") or _env("SUPABASE_KEY")
    telegram_bot_token: str = _env("TELEGRAM_BOT_TOKEN")
    sync_token: str = _env("SYNC_TOKEN")
    admin_token: str = _env("ADMIN_TOKEN")
    reader_preview_token: str = _env("READER_PREVIEW_TOKEN")
    reader_coins_enabled: bool = _env("READER_COINS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    reader_coin_grants_enabled: bool = _env("READER_COIN_GRANTS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    qinghe_commerce_shared_secret: str = _env("QINGHE_COMMERCE_SHARED_SECRET")
    qinghe_commerce_service_id: str = _env("QINGHE_COMMERCE_SERVICE_ID", "qinghe-api")
    reader_coin_max_single_grant: int = int(_env("READER_COIN_MAX_SINGLE_GRANT", "100000") or "100000")
    reader_commerce_clock_skew_seconds: int = int(_env("READER_COMMERCE_CLOCK_SKEW_SECONDS", "300") or "300")
    reader_commerce_nonce_ttl_seconds: int = int(_env("READER_COMMERCE_NONCE_TTL_SECONDS", "600") or "600")
    session_secret: str = _env("SESSION_SECRET")
    main_chat_id: str = _env("MAIN_CHAT_ID", "2608069201")
    main_group_invite_url: str = _env("MAIN_GROUP_INVITE_URL", "https://t.me/+Z5b3eeJjJTs0MTli")
    traveler_chat_id: str = _env("TRAVELER_CHAT_ID", "3769149961")
    keeper_chat_id: str = _env("KEEPER_CHAT_ID", "4366591335")
    traveler_chat_ids_raw: str = _env("TRAVELER_CHAT_IDS")
    keeper_chat_ids_raw: str = _env("KEEPER_CHAT_IDS")
    boosty_traveler_chat_id: str = _env("BOOSTY_TRAVELER_CHAT_ID")
    boosty_keeper_chat_id: str = _env("BOOSTY_KEEPER_CHAT_ID")
    auth_session_ttl_seconds: int = int(_env("AUTH_SESSION_TTL_SECONDS", "900") or "900")
    telegram_init_data_max_age_seconds: int = int(_env("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS", "86400") or "86400")
    membership_cache_seconds: int = int(_env("MEMBERSHIP_CACHE_SECONDS", "300") or "300")
    tribute_api_key: str = _env("TRIBUTE_API_KEY")
    tribute_traveler_subscription_id: str = _env("TRIBUTE_TRAVELER_SUBSCRIPTION_ID")
    tribute_keeper_subscription_id: str = _env("TRIBUTE_KEEPER_SUBSCRIPTION_ID")
    tribute_traveler_url: str = _env("TRIBUTE_TRAVELER_URL", "https://t.me/tribute/app?startapp=sZmh")
    tribute_keeper_url: str = _env("TRIBUTE_KEEPER_URL", "https://t.me/tribute/app?startapp=sZLB")
    access_debug_enabled: bool = _env("ACCESS_DEBUG_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    admin_session_ttl_seconds: int = int(_env("ADMIN_SESSION_TTL_SECONDS", "43200") or "43200")
    catalog_cache_seconds: int = int(_env("CATALOG_CACHE_SECONDS", "300") or "300")
    telegraph_cache_seconds: int = int(_env("TELEGRAPH_CACHE_SECONDS", "1800") or "1800")
    image_cache_seconds: int = int(_env("IMAGE_CACHE_SECONDS", "1800") or "1800")
    sync_max_prune_ratio: float = float(_env("SYNC_MAX_PRUNE_RATIO", "0.35") or "0.35")

    rate_limit_enabled: bool = _env("RATE_LIMIT_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    rate_limit_window_seconds: int = int(_env("RATE_LIMIT_WINDOW_SECONDS", "60") or "60")
    rate_limit_public_max_requests: int = int(_env("RATE_LIMIT_PUBLIC_MAX_REQUESTS", "240") or "240")
    rate_limit_sensitive_max_requests: int = int(_env("RATE_LIMIT_SENSITIVE_MAX_REQUESTS", "60") or "60")
    static_cache_seconds: int = int(_env("STATIC_CACHE_SECONDS", "86400") or "86400")
    # compatibility markers: v188-locked-preview-off-readable-soon; v192-bidirectional-infinite-reader;
    # v202-swipe-animation-feedback; v208-readable-chapter-title-center; v221-library-tags-paywall-dedup;
    # v224-compact-subscription-gate; v225-theme-sections-controls-settings;
    # v231-free-release-date-subscription-only-extra
    app_version: str = _env("APP_VERSION", "v245-user-subscriptions-schema-compat")
    app_events_enabled: bool = _env("APP_EVENTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    app_metrics_enabled: bool = _env("APP_METRICS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

    @property
    def normalized_main_chat_id(self) -> str:
        return normalize_telegram_chat_id(self.main_chat_id)

    @property
    def normalized_traveler_chat_id(self) -> str:
        return normalize_telegram_chat_id(self.traveler_chat_id)

    @property
    def normalized_keeper_chat_id(self) -> str:
        return normalize_telegram_chat_id(self.keeper_chat_id)

    @property
    def normalized_boosty_traveler_chat_id(self) -> str:
        return normalize_telegram_chat_id(self.boosty_traveler_chat_id)

    @property
    def normalized_boosty_keeper_chat_id(self) -> str:
        return normalize_telegram_chat_id(self.boosty_keeper_chat_id)

    @property
    def traveler_chat_ids(self) -> tuple[str, ...]:
        fallback = ",".join(filter(None, (self.traveler_chat_id, self.boosty_traveler_chat_id)))
        return normalize_telegram_chat_ids(self.traveler_chat_ids_raw, fallback)

    @property
    def keeper_chat_ids(self) -> tuple[str, ...]:
        fallback = ",".join(filter(None, (self.keeper_chat_id, self.boosty_keeper_chat_id)))
        return normalize_telegram_chat_ids(self.keeper_chat_ids_raw, fallback)

    def validate_production(self) -> list[str]:
        missing: list[str] = []
        for field_name in (
            "supabase_url",
            "supabase_service_key",
            "telegram_bot_token",
            "sync_token",
            "admin_token",
            "session_secret",
        ):
            if not getattr(self, field_name):
                missing.append(field_name.upper())
        if self.reader_coin_grants_enabled and not self.qinghe_commerce_shared_secret:
            missing.append("QINGHE_COMMERCE_SHARED_SECRET")
        return missing


settings = Settings()
