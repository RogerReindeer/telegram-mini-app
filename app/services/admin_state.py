"""Owner-facing project state summary for the Mini App admin panel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..cache import cache_stats
from ..config import settings
from ..database import db_select, supabase_ready
from .diagnostics import build_content_audit
from .production import build_production_report
from .metrics import metrics_snapshot


def _latest_sync_run() -> dict[str, Any] | None:
    if not supabase_ready():
        return None
    try:
        rows = db_select("sync_runs", order="started_at.desc", limit=1)
    except Exception:
        return None
    return rows[0] if rows else None


def _configured(value: Any) -> dict[str, Any]:
    return {"configured": bool(value), "status": "ok" if value else "missing"}


def build_admin_state() -> dict[str, Any]:
    """Return a compact launch-oriented admin dashboard payload."""
    audit = build_content_audit()
    production = build_production_report()
    latest_sync = _latest_sync_run()
    metrics = metrics_snapshot()
    production_summary = production.get("summary", {})
    content_counts = audit.get("counts", {})
    blockers = int(production_summary.get("fail", 0) or 0) + int(content_counts.get("errors", 0) or 0)
    warnings = int(production_summary.get("warn", 0) or 0) + int(content_counts.get("warnings", 0) or 0)
    return {
        "status": "blocked" if blockers else "attention" if warnings else "ok",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "app": {
            "version": settings.app_version,
            "environment": settings.app_env,
        },
        "configuration": {
            "supabase": _configured(settings.supabase_url and settings.supabase_service_key),
            "telegram_bot": _configured(settings.telegram_bot_token),
            "traveler_group": _configured(settings.normalized_traveler_chat_id),
            "keeper_group": _configured(settings.normalized_keeper_chat_id),
            "tribute_api": _configured(settings.tribute_api_key),
            "tribute_traveler": _configured(settings.tribute_traveler_subscription_id or settings.tribute_traveler_url),
            "tribute_keeper": _configured(settings.tribute_keeper_subscription_id or settings.tribute_keeper_url),
        },
        "content": content_counts,
        "sync": {
            "latest": latest_sync,
            "has_success": bool(latest_sync and str(latest_sync.get("status") or "").lower() in {"ok", "success"}),
        },
        "cache": cache_stats(),
        "metrics": {
            "events_total": metrics.get("events_total"),
            "recent_events": metrics.get("recent_events", [])[:10],
        },
        "next_actions": [
            "Run /api/sync/validate before /api/sync.",
            "Open one free chapter and one locked chapter inside Telegram Mini App.",
            "Check /api/admin/access/check for a real Telegram user before launch.",
        ],
        "release": {
            "blockers": blockers,
            "warnings": warnings,
            "production_status": production.get("status"),
            "content_status": audit.get("status"),
        },
    }
