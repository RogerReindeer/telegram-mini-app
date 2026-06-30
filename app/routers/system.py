from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..assets import static_manifest
from ..cache import cache_stats
from ..config import settings
from ..database import db_select, supabase_ready
from ..security import require_sync_token

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


@router.get("/ready")
def ready() -> dict[str, object]:
    missing = settings.validate_production()
    return {
        "status": "ready" if not missing else "degraded",
        "missing": missing,
        "supabase": supabase_ready(),
        "version": settings.app_version,
    }


@router.get("/version")
def version() -> dict[str, object]:
    return {
        "cache": cache_stats(),
        "version": settings.app_version,
        "app_version": settings.app_version,
        "environment": settings.app_env,
        "assets": static_manifest(),
    }


@router.get("/api/admin/sync/status")
def admin_sync_status(request: Request, token: str = ""):
    require_sync_token(request, token)
    try:
        rows = db_select("sync_runs", order="started_at.desc", limit=10)
    except Exception as error:
        return JSONResponse({"status": "error", "detail": str(error), "items": []}, status_code=503)
    return {"status": "ok", "items": rows}
