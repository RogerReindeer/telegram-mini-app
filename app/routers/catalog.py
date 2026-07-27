from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import settings

from ..services.access import (
    access_copy,
    access_paywall_copy,
    apply_novel_status_access_boundaries,
    decide_chapter_access,
    novel_status_boundary_count_hint,
)
from ..services.auth import public_viewer, viewer_access_profile, viewer_fast_access_profile, viewer_from_request
from ..services.catalog import get_all_novels, get_chapter_by_id, get_chapters_for_novel_ids, get_fox, get_novel_by_id, get_novel_by_slug, get_novel_chapters
from ..services.reader import (
    build_chapter_display_list_for_access,
    get_chapter_index_info_for_access,
    get_neighbor_chapters_for_access,
    get_next_locked_chapter_for_access,
    prepare_chapter_for_access_template,
    prepare_library_novels_for_access,
    prepare_novel_for_template,
)
from ..services.telegraph import fetch_chapter_content


def _counter_recovery_novel_ids(novels: list[dict]) -> list[str]:
    """Return novels whose stored counters disagree with NovelStatus endpoints."""
    result: list[str] = []
    for novel in novels:
        traveler_boundary = novel.get("traveler_access_through")
        keeper_boundary = novel.get("keeper_access_through") or traveler_boundary
        traveler_stored = int(novel.get("traveler_chapters_count") or novel.get("subscriber_chapters") or 0)
        keeper_stored = int(novel.get("keeper_chapters_count") or novel.get("keeper_chapters") or 0)
        traveler_hint = novel_status_boundary_count_hint(traveler_boundary)
        keeper_hint = novel_status_boundary_count_hint(keeper_boundary)
        novel_id = str(novel.get("novel_id") or novel.get("id") or "").strip()
        needs_recovery = bool(
            (traveler_boundary and traveler_stored != traveler_hint)
            or (keeper_boundary and keeper_stored != keeper_hint)
        )
        if novel_id and needs_recovery:
            result.append(novel_id)
    return result


def _library_recovery_chapters(novels: list[dict]) -> list[dict]:
    return get_chapters_for_novel_ids(_counter_recovery_novel_ids(novels))


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
        page_profile = viewer_fast_access_profile(viewer)
        fast_viewer = dict(viewer)
        fast_viewer["__fast_access_profile"] = page_profile
        try:
            novels = get_all_novels(include_hidden=False)
            prepared = prepare_library_novels_for_access(novels, _library_recovery_chapters(novels), fast_viewer)
        except Exception:
            prepared = []
        return templates.TemplateResponse(request, "library.html", {"app_title": app_title, "fox": get_fox(), "viewer": viewer, "novels": prepared})

    @router.get("/novel/{slug}")
    def novel(request: Request, slug: str):
        viewer = public_viewer(viewer_from_request(request))
        raw_novel = get_novel_by_slug(slug, include_hidden=False)
        if not raw_novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        novel_id = int(raw_novel.get("novel_id") or raw_novel.get("id") or 0) or None
        page_profile = viewer_fast_access_profile(viewer, novel_id)
        fast_viewer = dict(viewer)
        fast_viewer["__fast_access_profile"] = page_profile
        raw_chapters = get_novel_chapters(str(raw_novel.get("novel_id") or raw_novel.get("id")))
        raw_chapters = apply_novel_status_access_boundaries(raw_chapters, raw_novel)
        prepared_novels = prepare_library_novels_for_access([raw_novel], raw_chapters, fast_viewer)
        novel_prepared = prepared_novels[0] if prepared_novels else prepare_novel_for_template(raw_novel)
        chapters, hidden_subscriber_count = build_chapter_display_list_for_access(raw_chapters, raw_novel, page_profile)
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
        raw_chapters = apply_novel_status_access_boundaries(raw_chapters, raw_novel)
        raw_chapter = next(
            (
                chapter
                for chapter in raw_chapters
                if str(chapter.get("chapter_id") or chapter.get("id") or "") == chapter_id
            ),
            raw_chapter,
        )
        profile = viewer_fast_access_profile(viewer, int(raw_chapter.get("novel_id") or 0) or None)
        access_decision = decide_chapter_access(raw_chapter, raw_novel, profile)
        decision = access_decision
        prepared_chapter = prepare_chapter_for_access_template(raw_chapter, raw_novel, profile)
        prepared_novel = prepare_novel_for_template(raw_novel)
        info = get_chapter_index_info_for_access(raw_chapters, chapter_id, raw_novel, profile)
        previous_chapter, next_chapter = get_neighbor_chapters_for_access(raw_chapters, chapter_id, raw_novel, profile)
        next_locked_chapter = (
            get_next_locked_chapter_for_access(raw_chapters, chapter_id, raw_novel, profile)
            if decision.allowed
            else None
        )
        telegraph_content, telegraph_error = (None, "")
        if decision.allowed and decision.url:
            telegraph_content, telegraph_error = fetch_chapter_content(decision.url)
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
            "telegraph_error": telegraph_error,
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
            "next_locked_chapter": next_locked_chapter,
        })

    @router.get("/api/library")
    def api_library(request: Request):
        viewer = public_viewer(viewer_from_request(request))
        raw_novels = get_all_novels(include_hidden=False)
        novels = prepare_library_novels_for_access(
            raw_novels, _library_recovery_chapters(raw_novels), viewer
        )
        return {"items": novels}

    return router
