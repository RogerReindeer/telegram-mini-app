from __future__ import annotations
from fastapi import APIRouter
from ..config import settings
from ..assets import manifest
router = APIRouter()
@router.get('/health')
def health(): return {"status": "ok"}
@router.get('/ready')
def ready(): return {"status": "ready" if settings.sync_token else "degraded", "app_version": settings.app_version, "supabase_configured": settings.supabase_configured}
@router.get('/version')
def version(): return {"app_title": settings.app_title, "app_version": settings.app_version, "assets": manifest()}
