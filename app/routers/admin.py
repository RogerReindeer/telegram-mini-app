"""Admin diagnostics routes protected by SYNC_TOKEN.

These endpoints are intentionally read-only, except for explicit cache clearing.
They never expose tokens, Telegram initData, or Supabase service keys.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..cache import cache_stats, clear_all_caches, clear_catalog_cache, clear_image_cache, clear_telegraph_cache
from ..security import require_sync_token
from ..services.diagnostics import build_catalog_export, build_content_audit
from ..services.production import build_production_report
from ..services.metrics import metrics_snapshot, reset_metrics
from ..services.render_smoke import render_smoke_plan

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

@router.get("/production/check")
async def production_check(request: Request, token: str | None = Query(default=None)):
    _require_admin(request, token)
    return build_production_report()



@router.get("/metrics/summary")
async def metrics_summary(request: Request, token: str | None = Query(default=None)):
    _require_admin(request, token)
    return metrics_snapshot()


@router.get("/events/recent")
async def recent_events(request: Request, token: str | None = Query(default=None)):
    _require_admin(request, token)
    snapshot = metrics_snapshot()
    return {
        "status": "ok",
        "checked_at": snapshot.get("checked_at"),
        "recent_events": snapshot.get("recent_events", []),
        "note": "Events are in-memory and reset after redeploy/restart; secrets and raw payloads are not stored.",
    }


@router.post("/metrics/reset")
async def metrics_reset(request: Request, token: str | None = Query(default=None)):
    _require_admin(request, token)
    return reset_metrics()


@router.get("/export/manifest")
async def export_manifest(request: Request, token: str | None = Query(default=None)):
    _require_admin(request, token)
    catalog = build_catalog_export()
    return {
        "status": "ok",
        "kind": "catalog_export_manifest",
        "counts": catalog.get("counts", {}),
        "exported_at": catalog.get("exported_at"),
        "restore_scope": ["novels", "chapters", "fox"],
        "not_included": ["user progress", "payments", "subscriptions", "tokens", "sync_runs"],
        "warning": "This catalog export is not a full Supabase backup.",
    }


@router.get("/render/smoke-plan")
async def render_smoke_plan_endpoint(
    request: Request,
    token: str | None = Query(default=None),
    base_url: str | None = Query(default=None),
):
    _require_admin(request, token)
    return render_smoke_plan(base_url=base_url or "")


@router.get("/release/check")
async def release_check(request: Request, token: str | None = Query(default=None)):
    _require_admin(request, token)
    production = build_production_report()
    audit = build_content_audit()
    blockers = int(production.get("summary", {}).get("fail", 0) or 0) + int(audit.get("counts", {}).get("errors", 0) or 0)
    warnings = int(production.get("summary", {}).get("warn", 0) or 0) + int(audit.get("counts", {}).get("warnings", 0) or 0)
    return {
        "status": "blocked" if blockers else "ready_with_warnings" if warnings else "ready",
        "blockers": blockers,
        "warnings": warnings,
        "production_summary": production.get("summary", {}),
        "content_counts": audit.get("counts", {}),
        "required_manual_checks": [
            "Open Mini App inside Telegram on a real phone",
            "Run sync validate from Google Sheets",
            "Open one free chapter and one locked chapter",
            "Check Telegram group membership access",
            "Check Boosty/Tribute payment path manually before launch",
        ],
    }
