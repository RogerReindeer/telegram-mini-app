from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ..assets import static_manifest
from ..cache import cache_stats
from ..config import settings
from ..database import db_select, supabase_ready
from ..security import require_sync_token
from ..services.auth import (
    KEEPER_CHAT_ID,
    TELEGRAM_BOT_TOKEN,
    TRAVELER_CHAT_ID,
    TRIBUTE_API_KEY,
    TRIBUTE_KEEPER_SUBSCRIPTION_ID,
    TRIBUTE_TRAVELER_SUBSCRIPTION_ID,
)


router = APIRouter()


def _configuration_status() -> dict[str, str | bool]:
    return {
        "supabase": "ok" if supabase_ready() else "not_configured",
        "telegram_bot": "ok" if TELEGRAM_BOT_TOKEN else "not_configured",
        "traveler_chat": "ok" if TRAVELER_CHAT_ID else "not_configured",
        "keeper_chat": "ok" if KEEPER_CHAT_ID else "not_configured",
        "traveler_chat_id_normalized": bool(TRAVELER_CHAT_ID),
        "keeper_chat_id_normalized": bool(KEEPER_CHAT_ID),
        "tribute_webhook": "ok" if TRIBUTE_API_KEY else "not_configured",
        "tribute_traveler_plan": "ok" if TRIBUTE_TRAVELER_SUBSCRIPTION_ID else "not_configured",
        "tribute_keeper_plan": "ok" if TRIBUTE_KEEPER_SUBSCRIPTION_ID else "not_configured",
    }


def _public_sync_run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sync_id": row.get("sync_id") or row.get("id"),
        "source": row.get("source"),
        "status": row.get("status"),
        "schema_version": row.get("schema_version"),
        "novels_received": row.get("novels_received"),
        "chapters_received": row.get("chapters_received"),
        "fox_received": row.get("fox_received"),
        "novels_upserted": row.get("novels_upserted"),
        "chapters_upserted": row.get("chapters_upserted"),
        "fox_upserted": row.get("fox_upserted"),
        "warnings_count": row.get("warnings_count"),
        "error_message": row.get("error_message"),
        "started_at": row.get("started_at") or row.get("created_at"),
        "finished_at": row.get("finished_at") or row.get("updated_at"),
    }


@router.get("/health")
async def health():
    return {
        "status": "ok",
        **_configuration_status(),
        "cache": cache_stats(),
    }


@router.get("/ready")
async def ready():
    db_ready = supabase_ready()
    missing = settings.validate_production() if settings.app_env == "production" else []
    return {
        "status": "ok" if db_ready and not missing else "degraded",
        "supabase": "ok" if db_ready else "not_configured",
        "missing_required_env": missing,
        "cache": cache_stats(),
        "rate_limit": {
            "enabled": settings.rate_limit_enabled,
            "window_seconds": settings.rate_limit_window_seconds,
            "public_max_requests": settings.rate_limit_public_max_requests,
            "sensitive_max_requests": settings.rate_limit_sensitive_max_requests,
        },
    }


@router.get("/version")
async def version():
    return {
        "app": "telegram-mini-app",
        "version": settings.app_version,
        "schema_version": "v30+v31_user_state",
        "environment": settings.app_env,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "assets": static_manifest(),
    }


@router.get("/api/admin/sync/status")
async def admin_sync_status(request: Request, token: str | None = Query(default=None), limit: int = Query(default=5, ge=1, le=20)):
    """Return recent sync runs for admin diagnostics without exposing secrets."""
    require_sync_token(request, token)
    if not supabase_ready():
        raise HTTPException(status_code=503, detail="Supabase env vars are not configured")
    rows = db_select("sync_runs", order="started_at.desc", limit=limit)
    return {
        "status": "ok",
        "runs": [_public_sync_run(row) for row in rows],
        "cache": cache_stats(),
    }
