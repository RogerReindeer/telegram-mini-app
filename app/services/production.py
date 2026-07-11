"""Production readiness checks for the Mini App.

The checks are deliberately read-only and return owner-facing diagnostics
without exposing secrets.  They are meant to be opened before deploy or after a
large sync to catch configuration/content issues early.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..assets import static_manifest
from ..cache import cache_stats
from ..config import settings
from ..database import db_select, supabase_ready
from .diagnostics import build_content_audit

Check = dict[str, Any]


def _check(name: str, status: str, message: str, *, severity: str = "error", details: dict[str, Any] | None = None) -> Check:
    return {
        "name": name,
        "status": status,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def _env_checks() -> list[Check]:
    checks: list[Check] = []
    required = {
        "SUPABASE_URL": settings.supabase_url,
        "SUPABASE_SERVICE_KEY": settings.supabase_service_key,
        "SYNC_TOKEN": settings.sync_token,
        "SESSION_SECRET": settings.session_secret,
        "TELEGRAM_BOT_TOKEN": settings.telegram_bot_token,
    }
    for env_name, value in required.items():
        checks.append(_check(
            f"env.{env_name}",
            "pass" if bool(value) else "fail",
            f"{env_name} настроен." if value else f"{env_name} не настроен.",
        ))

    optional = {
        "TRAVELER_CHAT_IDS": ",".join(settings.traveler_chat_ids),
        "KEEPER_CHAT_IDS": ",".join(settings.keeper_chat_ids),
        "TRIBUTE_TRAVELER_URL": settings.tribute_traveler_url,
        "TRIBUTE_KEEPER_URL": settings.tribute_keeper_url,
    }
    for env_name, value in optional.items():
        checks.append(_check(
            f"env.{env_name}",
            "pass" if bool(value) else "warn",
            f"{env_name} настроен." if value else f"{env_name} не настроен. Это допустимо, если сценарий пока не используется.",
            severity="warning",
        ))

    if settings.access_debug_enabled and settings.app_env == "production":
        checks.append(_check(
            "env.ACCESS_DEBUG_ENABLED",
            "warn",
            "ACCESS_DEBUG_ENABLED включён в production. Лучше выключить после отладки.",
            severity="warning",
        ))
    else:
        checks.append(_check(
            "env.ACCESS_DEBUG_ENABLED",
            "pass",
            "Debug-доступ настроен безопасно для текущего окружения.",
            severity="warning",
        ))

    return checks


def _database_checks() -> list[Check]:
    checks: list[Check] = [
        _check(
            "database.supabase_ready",
            "pass" if supabase_ready() else "fail",
            "Supabase env vars заданы." if supabase_ready() else "Supabase env vars не заданы.",
        )
    ]
    if not supabase_ready():
        return checks

    for table in ("novels", "chapters", "user_novel_state", "user_chapter_progress", "sync_runs"):
        try:
            db_select(table, select="*", limit=1)
        except Exception as error:
            checks.append(_check(
                f"database.table.{table}",
                "fail",
                f"Таблица {table} недоступна: {error}",
            ))
        else:
            checks.append(_check(
                f"database.table.{table}",
                "pass",
                f"Таблица {table} доступна.",
            ))
    return checks


def _content_checks(audit: dict[str, Any]) -> list[Check]:
    counts = audit.get("counts") or {}
    errors = int(counts.get("errors") or 0)
    warnings = int(counts.get("warnings") or 0)
    novels = int(counts.get("novels") or 0)
    chapters = int(counts.get("chapters") or 0)
    visible = int(counts.get("visible_novels") or 0)

    checks = [
        _check(
            "content.audit_errors",
            "pass" if errors == 0 else "fail",
            "Критичных ошибок контента нет." if errors == 0 else f"Найдено критичных ошибок контента: {errors}.",
            details={"errors": errors},
        ),
        _check(
            "content.audit_warnings",
            "pass" if warnings == 0 else "warn",
            "Предупреждений контента нет." if warnings == 0 else f"Есть предупреждения контента: {warnings}.",
            severity="warning",
            details={"warnings": warnings},
        ),
        _check(
            "content.has_visible_novels",
            "pass" if visible > 0 else "fail",
            f"Видимых новелл: {visible}." if visible > 0 else "Нет видимых новелл.",
            details={"visible_novels": visible, "novels": novels},
        ),
        _check(
            "content.has_chapters",
            "pass" if chapters > 0 else "fail",
            f"Глав в Mini App: {chapters}." if chapters > 0 else "Нет глав в Mini App.",
            details={"chapters": chapters},
        ),
    ]
    return checks


def _runtime_checks() -> list[Check]:
    assets = static_manifest()
    checks = [
        _check(
            "runtime.version",
            "pass" if settings.app_version else "warn",
            f"APP_VERSION: {settings.app_version or 'не задан' }.",
            severity="warning",
        ),
        _check(
            "runtime.assets.style",
            "pass" if assets.get("style.css") else "fail",
            "style.css fingerprint найден." if assets.get("style.css") else "style.css fingerprint не найден.",
        ),
        _check(
            "runtime.assets.settings",
            "pass" if assets.get("settings.js") else "fail",
            "settings.js fingerprint найден." if assets.get("settings.js") else "settings.js fingerprint не найден.",
        ),
        _check(
            "runtime.rate_limit",
            "pass" if settings.rate_limit_enabled else "warn",
            "Rate limit включён." if settings.rate_limit_enabled else "Rate limit выключен.",
            severity="warning",
        ),
        _check(
            "runtime.static_cache",
            "pass" if settings.static_cache_seconds >= 300 else "warn",
            f"STATIC_CACHE_SECONDS={settings.static_cache_seconds}.",
            severity="warning",
        ),
    ]
    return checks


def _manual_checklist() -> list[dict[str, str]]:
    return [
        {"step": "Открыть /ready", "why": "Проверить Supabase и обязательные env vars."},
        {"step": "Открыть /version", "why": "Убедиться, что развернулась нужная версия и свежие hash CSS/JS."},
        {"step": "Запустить /api/admin/content/audit", "why": "Проверить ошибки в данных из таблицы."},
        {"step": "Запустить /api/sync/validate", "why": "Проверить payload Google Sheets без записи в БД."},
        {"step": "Сделать тестовый /api/sync", "why": "Убедиться, что sync_runs получает успешный запуск."},
        {"step": "Открыть библиотеку в Telegram WebView", "why": "Проверить реальные safe-area, тему и старый кеш WebView."},
        {"step": "Открыть бесплатную главу", "why": "Проверить Telegraph/Teletype, сохранение позиции и навигацию."},
        {"step": "Открыть закрытую главу", "why": "Проверить paywall copy и отсутствие случайного доступа."},
        {"step": "Проверить Telegram login", "why": "Убедиться, что initData/session работают на реальном Mini App."},
        {"step": "Проверить платёжный сценарий", "why": "Проверить Tribute/Boosty только если этот сценарий включён."},
    ]


def build_production_report() -> dict[str, Any]:
    """Build a safe readiness report for deployment diagnostics."""
    audit = build_content_audit()
    checks: list[Check] = []
    checks.extend(_env_checks())
    checks.extend(_database_checks())
    checks.extend(_content_checks(audit))
    checks.extend(_runtime_checks())

    failed = [item for item in checks if item.get("status") == "fail"]
    warned = [item for item in checks if item.get("status") == "warn"]
    status = "ready" if not failed else "blocked"
    if status == "ready" and warned:
        status = "ready_with_warnings"

    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "app": {
            "name": "telegram-mini-app",
            "version": settings.app_version,
            "environment": settings.app_env,
            "schema_version": "v30+v31_user_state",
        },
        "summary": {
            "checks": len(checks),
            "failed": len(failed),
            "warnings": len(warned),
            "passed": len([item for item in checks if item.get("status") == "pass"]),
        },
        "checks": checks,
        "content_audit_summary": {
            "status": audit.get("status"),
            "counts": audit.get("counts") or {},
        },
        "cache": cache_stats(),
        "assets": static_manifest(),
        "manual_checklist": _manual_checklist(),
    }
