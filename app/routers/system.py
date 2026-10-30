from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from ..assets import static_manifest
from ..cache import cache_stats
from ..config import settings
from ..database import db_select, supabase_ready
from ..security import require_admin_token

router = APIRouter()
SITE_ROOT = Path(__file__).resolve().parents[2]


@router.get("/startup-shell", include_in_schema=False)
def startup_shell() -> FileResponse:
    """Return the branded shell cached by the navigation service worker."""
    return FileResponse(
        SITE_ROOT / "launcher" / "index.html",
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
        },
    )


@router.get("/startup-sw.js", include_in_schema=False)
def startup_worker() -> FileResponse:
    """Serve the worker at the origin root so it may protect reader routes."""
    return FileResponse(
        SITE_ROOT / "static" / "startup-sw.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
        },
    )


@router.get("/health")
def health() -> JSONResponse:
    # Public CORS is intentional only for this non-sensitive liveness probe.
    # The always-on static launcher uses it to wake a sleeping Render Web Service
    # and waits for the real application before navigating the Telegram WebView.
    return JSONResponse(
        {"status": "ok", "version": settings.app_version},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Accept",
        },
    )


@router.get("/ready")
def ready() -> JSONResponse:
    missing = settings.validate_production()
    database_ready = supabase_ready()
    if database_ready and not missing:
        try:
            # A real PostgREST round trip catches revoked/expired keys and a
            # temporarily unavailable database; an empty catalog is still ready.
            db_select("novels", select="novel_id", limit=1)
        except Exception:
            database_ready = False
    is_ready = not missing and database_ready
    payload: dict[str, object] = {
        "status": "ready" if is_ready else "degraded",
        "missing": missing,
        "supabase": database_ready,
        "version": settings.app_version,
        "features": {
            "reader_coins": settings.reader_coins_enabled,
            "reader_coin_grants": settings.reader_coin_grants_enabled,
            "reader_test_free_coins": bool(getattr(settings, "reader_test_free_coins_enabled", False)),
            "reader_test_purchases": bool(getattr(settings, "reader_test_purchases_enabled", False)),
        },
    }
    return JSONResponse(payload, status_code=200 if is_ready else 503)


@router.get("/version")
def version() -> dict[str, object]:
    return {
        "cache": cache_stats(),
        "version": settings.app_version,
        "app_version": settings.app_version,
        "environment": settings.app_env,
        "assets": static_manifest(),
        "features": {
            "reader_coins": settings.reader_coins_enabled,
            "reader_coin_grants": settings.reader_coin_grants_enabled,
            "reader_test_free_coins": bool(getattr(settings, "reader_test_free_coins_enabled", False)),
            "reader_test_purchases": bool(getattr(settings, "reader_test_purchases_enabled", False)),
        },
    }


@router.get("/api/admin/sync/status")
def admin_sync_status(request: Request):
    require_admin_token(request)
    try:
        rows = db_select("sync_runs", order="started_at.desc", limit=10)
    except Exception as error:
        return JSONResponse({"status": "error", "detail": str(error), "items": []}, status_code=503)
    return {"status": "ok", "items": rows}
