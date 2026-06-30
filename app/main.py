from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from .assets import manifest, static_url
from .config import settings
from .database import DatabaseUnavailable, upsert
from .services import catalog

BASE_DIR = Path(__file__).resolve().parents[1]

templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
templates.env.globals['static_url'] = static_url

app = FastAPI(title=settings.app_title, version=settings.app_version)
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok', 'version': settings.app_version}


@app.get('/ready')
def ready() -> dict[str, object]:
    return {
        'status': 'ready' if settings.supabase_ready else 'degraded',
        'supabase': settings.supabase_ready,
        'version': settings.app_version,
    }


@app.get('/version')
def version() -> dict[str, object]:
    return {'app_version': settings.app_version, 'assets': manifest()}


@app.get('/')
def index(request: Request):
    return templates.TemplateResponse('index.html', {'request': request, 'app_title': settings.app_title, 'fox': {}, 'error': ''})


@app.get('/library')
def library(request: Request):
    error = ''
    try:
        novels = catalog.get_novels()
    except (DatabaseUnavailable, Exception) as exc:
        novels = []
        error = 'Библиотека не загрузилась: проверьте переменные Supabase и подключение.'
    visible = [n for n in novels if not n.get('is_hidden')]
    hidden = [n for n in novels if n.get('is_hidden')]
    return templates.TemplateResponse('library.html', {
        'request': request,
        'app_title': settings.app_title,
        'novels': visible,
        'hidden_novels': hidden,
        'fox': catalog.get_fox(),
        'telegram_channel_url': settings.telegram_channel_url,
        'error': error,
    })


@app.get('/novel/{slug}')
def novel_page(request: Request, slug: str):
    try:
        novel = catalog.get_novel(slug)
    except (DatabaseUnavailable, Exception):
        novel = None
    if not novel:
        raise HTTPException(status_code=404, detail='Novel not found')
    chapters = catalog.get_chapters(int(novel['id']))
    hidden_subscriber_count = len([c for c in chapters if c.get('is_paid_extra')])
    return templates.TemplateResponse('novel.html', {
        'request': request,
        'app_title': settings.app_title,
        'novel': novel,
        'chapters': chapters,
        'hidden_subscriber_count': hidden_subscriber_count,
        'fox': catalog.get_fox(),
        'viewer': {'role': 'guest'},
    })


@app.get('/chapter/{chapter_id}')
def chapter_page(request: Request, chapter_id: str):
    chapter = catalog.get_chapter(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail='Chapter not found')
    novel = None
    novel_id = chapter.get('novel_id') or chapter.get('NovelID')
    if novel_id:
        for item in catalog.get_novels():
            if int(item.get('id') or 0) == int(novel_id):
                novel = item
                break
    if not novel:
        novel = {'id': novel_id or 0, 'slug': 'library', 'display_title': 'Новелла'}
    return templates.TemplateResponse('chapter.html', {
        'request': request,
        'novel': novel,
        'chapter': chapter,
        'chapter_index': 1,
        'available_chapters': 1,
        'is_locked': not chapter.get('is_available'),
        'telegraph_content': {'content_html': '<p>Текст главы загружается из источника после подключения production-сервисов.</p>'},
        'telegraph_error': '',
        'preview_text': '',
        'access_copy': {'title': 'Глава закрыта', 'description': 'Проверьте доступ или дату открытия.'},
        'boosty_access_url': '',
        'tribute_access_url': '',
        'previous_chapter': None,
        'next_chapter': None,
        'fox': catalog.get_fox(),
        'viewer': {'role': 'guest'},
    })


@app.get('/api/library')
def api_library():
    try:
        return {'items': catalog.get_novels()}
    except Exception as exc:
        return JSONResponse({'error': 'library_unavailable'}, status_code=503)


def _check_sync_token(token: str | None, authorization: str | None) -> None:
    supplied = token or ''
    if authorization and authorization.lower().startswith('bearer '):
        supplied = authorization.split(' ', 1)[1].strip()
    if settings.sync_token and supplied != settings.sync_token:
        raise HTTPException(status_code=401, detail='Invalid sync token')


def _payload_rows(payload: dict, key: str) -> list[dict]:
    value = payload.get(key) or payload.get(key.capitalize()) or []
    return value if isinstance(value, list) else []


@app.post('/api/sync/validate')
def sync_validate(payload: dict, token: str | None = Query(default=None), authorization: str | None = Header(default=None)):
    _check_sync_token(token, authorization)
    novels = _payload_rows(payload, 'novels')
    chapters = _payload_rows(payload, 'chapters')
    fox = _payload_rows(payload, 'fox')
    issues = []
    for idx, row in enumerate(chapters, start=1):
        chapter_id = row.get('chapter_id') or row.get('ChapterID')
        if not chapter_id:
            issues.append({'severity': 'error', 'row': idx, 'field': 'ChapterID', 'message': 'ChapterID is required'})
    return {
        'ok': not issues,
        'mode': 'validate_only',
        'version': settings.app_version,
        'counts': {'novels': len(novels), 'chapters': len(chapters), 'fox': len(fox)},
        'issues': issues,
    }


@app.post('/api/sync')
def sync_write(payload: dict, token: str | None = Query(default=None), authorization: str | None = Header(default=None)):
    _check_sync_token(token, authorization)
    if not settings.supabase_ready:
        raise HTTPException(status_code=503, detail='Supabase is not configured')
    novels = _payload_rows(payload, 'novels')
    chapters = _payload_rows(payload, 'chapters')
    fox = _payload_rows(payload, 'fox')
    written = {
        'novels': len(upsert('novels', novels, 'id') if novels else []),
        'chapters': len(upsert('chapters', chapters, 'chapter_id') if chapters else []),
        'fox': len(upsert('fox', fox) if fox else []),
    }
    return {'ok': True, 'version': settings.app_version, 'written': written}
