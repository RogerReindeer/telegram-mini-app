from __future__ import annotations
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from ..templating import render_template
from ..config import settings
from ..security import require_sync_token
from ..cache import clear, stats
from ..services.diagnostics import project_state, content_audit, production_check
from ..services.catalog import list_novels, list_chapters, get_fox
router = APIRouter()
@router.get('/admin', response_class=HTMLResponse)
def admin_page(request: Request, token: str | None = Query(default=None)):
    require_sync_token(token)
    return render_template(request, 'admin.html', {"app_title": settings.app_title, "fox": get_fox(), "state": project_state(), "token": token or ""})
@router.get('/api/admin/state')
def state(token: str | None = Query(default=None)):
    require_sync_token(token); return project_state()
@router.get('/api/admin/content/audit')
def audit(token: str | None = Query(default=None)):
    require_sync_token(token); return content_audit()
@router.get('/api/admin/production/check')
def production(token: str | None = Query(default=None)):
    require_sync_token(token); return production_check()
@router.get('/api/admin/cache/status')
def cache_status(token: str | None = Query(default=None)):
    require_sync_token(token); return stats()
@router.post('/api/admin/cache/clear')
def cache_clear(token: str | None = Query(default=None)):
    require_sync_token(token); return {"cleared": clear()}
@router.get('/api/admin/export/catalog')
def export_catalog(token: str | None = Query(default=None)):
    require_sync_token(token)
    novels = list_novels()
    return {"novels": novels, "chapters": [ch for n in novels for ch in list_chapters(n['id'])], "fox": get_fox()}
@router.get('/api/admin/export/manifest')
def export_manifest(token: str | None = Query(default=None)):
    require_sync_token(token)
    return {"includes": ["novels", "chapters", "fox"], "excludes": ["user progress", "payments", "subscriptions", "secrets", "sync_runs"]}
