from __future__ import annotations

from fastapi import APIRouter, Request

from ..cache import cache_stats, clear_all_caches, clear_catalog_cache, clear_image_cache, clear_telegraph_cache
from ..security import require_sync_token
from ..services.admin_state import build_admin_state
from ..services.diagnostics import build_catalog_export, build_content_audit
from ..services.events import recent_events
from ..services.metrics import metrics_snapshot, reset_metrics
from ..services.production import build_production_report
from ..services.render_smoke import render_smoke_plan

router = APIRouter(prefix="/api/admin")


def _guard(request: Request, token: str) -> None:
    require_sync_token(request, token)


@router.get("/state")
def state(request: Request, token: str = ""):
    _guard(request, token)
    return build_admin_state()


@router.get("/access/check")
def access_check(request: Request, token: str = "", user_id: int | None = None):
    _guard(request, token)
    if not user_id:
        return {"status": "needs_user_id", "configuration": build_admin_state().get("access", {})}
    return {"status": "ok", "user_id": user_id, "configuration": build_admin_state().get("access", {})}


@router.get("/content/audit")
def content_audit(request: Request, token: str = ""):
    _guard(request, token)
    return build_content_audit()


@router.get("/export/catalog")
def export_catalog(request: Request, token: str = ""):
    _guard(request, token)
    return build_catalog_export()


@router.get("/export/manifest")
def export_manifest(request: Request, token: str = ""):
    _guard(request, token)
    return {"status": "ok", "exports": ["catalog"], "excluded": ["user progress", "payments", "subscriptions", "secrets", "sync_runs"]}


@router.get("/cache")
def cache(request: Request, token: str = ""):
    _guard(request, token)
    return cache_stats()


@router.post("/cache/clear")
def cache_clear(request: Request, token: str = "", namespace: str = "all"):
    _guard(request, token)
    cleared = {
        "catalog": clear_catalog_cache,
        "telegraph": clear_telegraph_cache,
        "images": clear_image_cache,
        "all": clear_all_caches,
    }.get(namespace, clear_all_caches)()
    return {"status": "ok", "namespace": namespace, "cleared": cleared}


@router.get("/production/check")
def production_check(request: Request, token: str = ""):
    _guard(request, token)
    return build_production_report()


@router.get("/release/check")
def release_check(request: Request, token: str = ""):
    _guard(request, token)
    production = build_production_report()
    production_summary = production.get("summary", {})
    failed = production_summary.get("failed", 0)
    warnings = production_summary.get("warnings", 0)
    return {"status": "ready" if failed == 0 else "blocked", "failed": failed, "warnings": warnings, "production": production}


@router.get("/render/smoke-plan")
def smoke_plan(request: Request, token: str = "", base_url: str = ""):
    _guard(request, token)
    return render_smoke_plan(base_url=base_url)


@router.get("/metrics/summary")
def metrics_summary(request: Request, token: str = ""):
    _guard(request, token)
    return metrics_snapshot()


@router.post("/metrics/reset")
def metrics_reset(request: Request, token: str = ""):
    _guard(request, token)
    return reset_metrics()


@router.get("/events/recent")
def events_recent(request: Request, token: str = ""):
    _guard(request, token)
    return {"status": "ok", "recent_events": recent_events()}
