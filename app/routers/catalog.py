from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import settings

from ..services.access import access_copy, access_paywall_copy, chapter_preview_url, decide_chapter_access
from ..services.auth import public_viewer, viewer_access_profile, viewer_from_request
from ..services.catalog import get_all_chapters, get_all_novels, get_chapter_by_id, get_fox, get_novel_by_id, get_novel_by_slug, get_novel_chapters
from ..services.reader import (
    build_chapter_display_list_for_access,
    get_chapter_index_info_for_access,
    get_neighbor_chapters_for_access,
    prepare_chapter_for_access_template,
    prepare_library_novels_for_access,
    prepare_novel_for_template,
)
from ..services.telegraph import fetch_locked_preview, fetch_telegraph_content


def create_catalog_router(*, templates: Jinja2Templates, app_title: str) -> APIRouter:
    router = APIRouter()

    @router.get("/", include_in_schema=False)
    def index(request: Request):
        # В Telegram Mini App не нужен промежуточный экран "загружается":
        # корень сразу ведёт в библиотеку. Шаблон index.html остаётся только
        # как безопасный HTML fallback для ошибок приложения.
        return RedirectResponse(url="/library", status_code=307)

    @router.get("/library")
    def library(request: Request):
        viewer = public_viewer(viewer_from_request(request))
        try:
            novels = get_all_novels(include_hidden=True)
            chapters = get_all_chapters()
            prepared = prepare_library_novels_for_access(novels, chapters, viewer)
        except Exception:
            prepared = []
        return templates.TemplateResponse(request, "library.html", {"app_title": app_title, "fox": get_fox(), "viewer": viewer, "novels": prepared})

    @router.get("/novel/{slug}")
    def novel(request: Request, slug: str):
        viewer = public_viewer(viewer_from_request(request))
        raw_novel = get_novel_by_slug(slug, include_hidden=True)
        if not raw_novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        raw_chapters = get_novel_chapters(str(raw_novel.get("novel_id") or raw_novel.get("id")))
        novel_prepared = prepare_novel_for_template(raw_novel)
        chapters, hidden_subscriber_count = build_chapter_display_list_for_access(raw_chapters, raw_novel, viewer)
        return templates.TemplateResponse(request, "novel.html", {
            "app_title": app_title,
            "fox": get_fox(),
            "viewer": viewer,
            "novel": novel_prepared,
            "chapters": chapters,
            "hidden_subscriber_count": hidden_subscriber_count,
        })

    @router.get("/chapter/{chapter_id}")
    def chapter(request: Request, chapter_id: str):
        viewer = public_viewer(viewer_from_request(request))
        raw_chapter = get_chapter_by_id(chapter_id)
        if not raw_chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        raw_novel = get_novel_by_id(str(raw_chapter.get("novel_id"))) or {}
        raw_chapters = get_novel_chapters(str(raw_chapter.get("novel_id")))
        profile = viewer_access_profile(viewer, int(raw_chapter.get("novel_id") or 0) or None)
        access_decision = decide_chapter_access(raw_chapter, raw_novel, profile)
        decision = access_decision
        prepared_chapter = prepare_chapter_for_access_template(raw_chapter, raw_novel, viewer)
        prepared_novel = prepare_novel_for_template(raw_novel)
        info = get_chapter_index_info_for_access(raw_chapters, chapter_id, raw_novel, viewer)
        previous_chapter, next_chapter = get_neighbor_chapters_for_access(raw_chapters, chapter_id, raw_novel, viewer)
        telegraph_content, telegraph_error = (None, "")
        preview_text, preview_error = ("", "")
        if decision.allowed and decision.url:
            telegraph_content, telegraph_error = fetch_telegraph_content(decision.url)
        elif chapter_preview_url(raw_chapter):
            preview_text, preview_error = fetch_locked_preview(raw_chapter)
        return templates.TemplateResponse(request, "chapter.html", {
            "app_title": app_title,
            "fox": get_fox(),
            "viewer": viewer,
            "novel": prepared_novel,
            "chapter": prepared_chapter,
            "chapter_index": info.get("chapter_index", 0),
            "available_chapters": info.get("available_chapters", 0),
            "is_locked": not decision.allowed,
            "telegraph_content": telegraph_content,
            "telegraph_error": telegraph_error or preview_error,
            "preview_text": preview_text,
            "access_copy": access_copy(decision.required_role),
            "access_paywall": access_paywall_copy(decision, raw_novel, profile),
            "boosty_access_url": "",
            "tribute_access_url": settings.tribute_keeper_url or settings.tribute_traveler_url,
            "tribute_traveler_url": settings.tribute_traveler_url,
            "tribute_keeper_url": settings.tribute_keeper_url,
            "traveler_chat_id": settings.normalized_traveler_chat_id,
            "keeper_chat_id": settings.normalized_keeper_chat_id,
            "previous_chapter": previous_chapter,
            "next_chapter": next_chapter,
        })

    @router.get("/api/library")
    def api_library(request: Request):
        viewer = public_viewer(viewer_from_request(request))
        novels = prepare_library_novels_for_access(get_all_novels(include_hidden=True), get_all_chapters(), viewer)
        return {"items": novels}

    return router
