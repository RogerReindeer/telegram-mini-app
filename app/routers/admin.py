"""Admin diagnostics routes protected by SYNC_TOKEN.

These endpoints are intentionally read-only, except for explicit cache clearing.
They never expose tokens, Telegram initData, or Supabase service keys.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..cache import cache_stats, clear_all_caches, clear_catalog_cache, clear_image_cache, clear_telegraph_cache
from ..security import require_sync_token
from ..services.diagnostics import build_catalog_export, build_content_audit

router = APIRouter(prefix="/api/admin")


def _require_admin(request: Request, token: str | None) -> None:
    require_sync_token(request, token)


@router.get("/content/audit")
async def content_audit(request: Request, token: str | None = Query(default=None)):
    _require_admin(request, token)
    return build_content_audit()


@router.get("/export/catalog")
async def export_catalog(request: Request, token: str | None = Query(default=None)):
    _require_admin(request, token)
    return build_catalog_export()


@router.get("/cache")
async def admin_cache_status(request: Request, token: str | None = Query(default=None)):
    _require_admin(request, token)
    return {"status": "ok", "cache": cache_stats()}


@router.post("/cache/clear")
async def admin_cache_clear(
    request: Request,
    token: str | None = Query(default=None),
    namespace: str = Query(default="all", pattern="^(all|catalog|telegraph|images)$"),
):
    _require_admin(request, token)
    if namespace == "catalog":
        cleared = clear_catalog_cache()
    elif namespace == "telegraph":
        cleared = clear_telegraph_cache()
    elif namespace == "images":
        cleared = clear_image_cache()
    else:
        cleared = clear_all_caches()
    return {"status": "ok", "namespace": namespace, "cleared": cleared, "cache": cache_stats()}
