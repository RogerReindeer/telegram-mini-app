from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..cache import cache_stats, clear_all_caches, clear_catalog_cache, clear_image_cache, clear_telegraph_cache
from ..security import require_admin_token
from ..schemas_commerce import (
    BulkNovelPricingPayload,
    SelectedChapterPricingPayload,
    StoreProductAdminPayload,
    TestPurchaseRollbackRequest,
)
from ..services.admin_state import build_admin_state
from ..services.analytics import build_analytics_summary, personal_reading_stats
from ..services.diagnostics import build_catalog_export, build_content_audit
from ..services.events import recent_events
from ..services.metrics import metrics_snapshot, reset_metrics
from ..services.production import build_production_report
from ..services.render_smoke import render_smoke_plan
from ..services.auth import invalidate_access_cache
from ..services.coins import (
    StoreTemporaryError,
    StoreValidationError,
    list_novel_pricing_rules,
    list_store_pricing_catalog,
    list_store_products,
    rollback_test_purchases,
    set_bulk_novel_pricing,
    set_selected_chapter_prices,
    upsert_store_product,
)

router = APIRouter(prefix="/api/admin")


def _guard(request: Request) -> None:
    require_admin_token(request)


@router.get("/state")
def state(request: Request):
    _guard(request)
    return build_admin_state()


@router.get("/access/check")
def access_check(request: Request, user_id: int | None = None):
    _guard(request)
    if not user_id:
        return {"status": "needs_user_id", "configuration": build_admin_state().get("access", {})}
    return {"status": "ok", "user_id": user_id, "configuration": build_admin_state().get("access", {})}


@router.get("/content/audit")
def content_audit(request: Request):
    _guard(request)
    return build_content_audit()


@router.get("/export/catalog")
def export_catalog(request: Request):
    _guard(request)
    return build_catalog_export()


@router.get("/export/manifest")
def export_manifest(request: Request):
    _guard(request)
    return {"status": "ok", "exports": ["catalog"], "excluded": ["user progress", "payments", "subscriptions", "secrets", "sync_runs"]}


@router.get("/cache")
def cache(request: Request):
    _guard(request)
    return cache_stats()


@router.post("/cache/clear")
def cache_clear(request: Request, namespace: str = "all"):
    _guard(request)
    cleared = {
        "catalog": clear_catalog_cache,
        "telegraph": clear_telegraph_cache,
        "images": clear_image_cache,
        "all": clear_all_caches,
    }.get(namespace, clear_all_caches)()
    return {"status": "ok", "namespace": namespace, "cleared": cleared}


@router.get("/production/check")
def production_check(request: Request):
    _guard(request)
    return build_production_report()


@router.get("/release/check")
def release_check(request: Request):
    _guard(request)
    production = build_production_report()
    production_summary = production.get("summary", {})
    failed = production_summary.get("failed", 0)
    warnings = production_summary.get("warnings", 0)
    return {"status": "ready" if failed == 0 else "blocked", "failed": failed, "warnings": warnings, "production": production}


@router.get("/render/smoke-plan")
def smoke_plan(request: Request, base_url: str = ""):
    _guard(request)
    return render_smoke_plan(base_url=base_url)


@router.get("/metrics/summary")
def metrics_summary(request: Request):
    _guard(request)
    return metrics_snapshot()


@router.post("/metrics/reset")
def metrics_reset(request: Request):
    _guard(request)
    return reset_metrics()


@router.get("/events/recent")
def events_recent(request: Request):
    _guard(request)
    return {"status": "ok", "recent_events": recent_events()}


@router.get("/analytics/summary")
def analytics_summary(request: Request, days: int = 30):
    _guard(request)
    return build_analytics_summary(days=days)


@router.get("/analytics/user/{user_id}")
def analytics_user(request: Request, user_id: int):
    _guard(request)
    return {"status": "ok", "user_id": user_id, "reading": personal_reading_stats(user_id)}


@router.get("/store/products")
def store_products(request: Request):
    _guard(request)
    try:
        return {"status": "ok", "exchange_rate_rub": 1, "items": list_store_products(active_only=False)}
    except Exception as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error


@router.put("/store/products/{product_code}")
def store_product_upsert(request: Request, product_code: str, model: StoreProductAdminPayload):
    _guard(request)
    try:
        product = upsert_store_product(product_code, model.model_dump())
    except StoreValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except StoreTemporaryError as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error
    return {"status": "ok", "product": product}


@router.get("/store/pricing-rules")
def store_pricing_rules(request: Request):
    _guard(request)
    try:
        return {"status": "ok", "exchange_rate_rub": 1, "items": list_novel_pricing_rules()}
    except StoreTemporaryError as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error


@router.get("/store/pricing-catalog")
def store_pricing_catalog(request: Request):
    _guard(request)
    try:
        return list_store_pricing_catalog()
    except StoreTemporaryError as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error


@router.post("/store/bulk-pricing")
def store_bulk_pricing(request: Request, model: BulkNovelPricingPayload):
    _guard(request)
    try:
        return set_bulk_novel_pricing(
            model.novel_ids,
            model.chapter_coin_price,
            model.bundle_coin_price,
        )
    except StoreValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except StoreTemporaryError as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error


@router.post("/store/chapter-pricing")
def store_chapter_pricing(request: Request, model: SelectedChapterPricingPayload):
    _guard(request)
    try:
        return set_selected_chapter_prices(
            model.chapter_ids,
            model.coin_price,
            reset_to_default=model.reset_to_default,
        )
    except StoreValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except StoreTemporaryError as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error


@router.post("/store/rollback-test-purchases")
def store_rollback_test_purchases(request: Request, model: TestPurchaseRollbackRequest):
    _guard(request)
    try:
        result = rollback_test_purchases(model.telegram_user_id)
    except StoreValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except StoreTemporaryError as error:
        raise HTTPException(status_code=503, detail="store_temporarily_unavailable") from error
    invalidate_access_cache(model.telegram_user_id)
    return result
