from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from ..config import settings
from ..services.auth import viewer_from_request
from ..services.catalog import get_fox, get_novel_by_slug, list_novels, list_chapters, find_chapter
from ..services.reader import prepare_library, prepare_novel, prepare_chapter
router = APIRouter()

def templates(request: Request):
    return request.app.state.templates

@router.get('/', response_class=HTMLResponse)
def index(request: Request):
    return templates(request).TemplateResponse('index.html', {"request": request, "app_title": settings.app_title, "fox": get_fox(), "error": None})

@router.get('/library', response_class=HTMLResponse)
def library(request: Request):
    viewer = viewer_from_request(request)
    data = prepare_library(viewer)
    return templates(request).TemplateResponse('library.html', {"request": request, "app_title": settings.app_title, "fox": get_fox(), "viewer": viewer, **data})

@router.get('/novel/{slug}', response_class=HTMLResponse)
def novel_page(request: Request, slug: str):
    novel = get_novel_by_slug(slug)
    if not novel: raise HTTPException(status_code=404, detail='Novel not found')
    viewer = viewer_from_request(request)
    data = prepare_novel(novel, viewer)
    return templates(request).TemplateResponse('novel.html', {"request": request, "app_title": settings.app_title, "fox": get_fox(), "viewer": viewer, "novel": novel, **data})

@router.get('/chapter/{chapter_id}', response_class=HTMLResponse)
def chapter_page(request: Request, chapter_id: str):
    found = find_chapter(chapter_id)
    if not found: raise HTTPException(status_code=404, detail='Chapter not found')
    novel, chapter, index = found
    viewer = viewer_from_request(request)
    chapters = list_chapters(novel['id'])
    data = prepare_chapter(novel, chapter, chapters, index, viewer)
    return templates(request).TemplateResponse('chapter.html', {"request": request, "app_title": settings.app_title, "fox": get_fox(), "viewer": viewer, "novel": novel, "chapter": chapter, "boosty_access_url": settings.boosty_traveler_url, **data})

@router.get('/api/catalog/novels')
def api_novels(): return {"novels": list_novels()}

@router.get('/api/catalog/novels/{slug}')
def api_novel(slug: str):
    novel = get_novel_by_slug(slug)
    if not novel: raise HTTPException(status_code=404, detail='Novel not found')
    return {"novel": novel, "chapters": list_chapters(novel['id'])}
