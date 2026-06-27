from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..services.auth import (
    TRIBUTE_KEEPER_URL,
    public_viewer,
    viewer_from_request,
)
from ..services.catalog import (
    get_all_chapters,
    get_all_novels,
    get_chapter_by_id,
    get_fox,
    get_novel_by_id,
    get_novel_by_slug,
    get_novel_chapters,
)
from ..services.reader import (
    access_copy,
    can_view_novel_for_profile,
    clean_value,
    count_available_chapter_units_for_access,
    count_chapter_units_for_card,
    decide_chapter_access,
    effective_role_for_novel,
    finalize_novel_access_summary,
    get_chapter_index_info_for_access,
    get_neighbor_chapters_for_access,
    normalize_required_role,
    novel_required_role,
    prepare_chapter_for_access_template,
    prepare_chapter_for_template,
    prepare_library_novels_for_access,
    prepare_novel_for_template,
    to_bool,
    viewer_can_access_required_role,
    build_chapter_display_list_for_access,
    chapter_content_url_for_access,
)
from ..services.telegraph import fetch_locked_preview, fetch_telegraph_content


def create_catalog_router(*, templates: Any, app_title: str) -> APIRouter:
    """Public pages and read-only catalog API routes."""

    router = APIRouter()

    @router.get("/")
    async def home():
        return RedirectResponse(url="/library")

    @router.get("/library")
    async def library(request: Request):
        viewer = viewer_from_request(request)
        include_hidden = viewer.get("role") == "keeper"
        novels = get_all_novels(include_hidden=include_hidden)
        chapters = get_all_chapters()
        fox = get_fox()
        prepared_novels = prepare_library_novels_for_access(novels, chapters, viewer)
        return templates.TemplateResponse(
            request,
            "library.html",
            {"app_title": app_title, "novels": prepared_novels, "fox": fox, "viewer": public_viewer(viewer)},
        )

    @router.get("/novel/{slug}")
    async def novel_page(request: Request, slug: str):
        viewer = viewer_from_request(request)
        viewer_role = str(viewer.get("role") or "guest")
        novel = get_novel_by_slug(slug, include_hidden=viewer_role == "keeper")
        if not novel:
            raise HTTPException(status_code=404, detail="Новелла не найдена")
        if not to_bool(novel.get("is_visible"), True) and viewer_role != "keeper":
            raise HTTPException(status_code=404, detail="Новелла не найдена")
        viewer_role, access_profile = effective_role_for_novel(viewer, novel)
        if not can_view_novel_for_profile(novel, access_profile):
            raise HTTPException(status_code=403, detail="Эта новелла доступна подписчикам")
        fox = get_fox()
        all_chapters = get_novel_chapters(clean_value(novel.get("id")))
        prepared_novel = prepare_novel_for_template(novel)
        prepared_novel["required_role"] = novel_required_role(novel)
        prepared_novel["viewer_has_book_access"] = viewer_can_access_required_role(
            viewer_role, prepared_novel["required_role"]
        )
        prepared_novel["display_chapters_count"] = (
            count_chapter_units_for_card(all_chapters) or prepared_novel["total_chapters"] or 0
        )
        prepared_novel["free_chapters_count"] = count_available_chapter_units_for_access(
            all_chapters, novel, {"role": "guest", "has_full_book_access": False}
        )
        prepared_novel["traveler_chapters_count"] = prepared_novel["free_chapters_count"]
        prepared_novel["keeper_chapters_count"] = count_available_chapter_units_for_access(
            all_chapters, novel, {"role": "keeper", "has_full_book_access": False}
        )
        prepared_novel["available_chapters_count"] = count_available_chapter_units_for_access(
            all_chapters, novel, access_profile
        )
        finalize_novel_access_summary(prepared_novel)
        visible_chapters = (
            all_chapters if viewer_role == "keeper" else [chapter for chapter in all_chapters if chapter.get("is_visible") is True]
        )
        display_chapters, hidden_subscriber_count = build_chapter_display_list_for_access(
            visible_chapters, novel, access_profile
        )
        return templates.TemplateResponse(
            request,
            "novel.html",
            {
                "app_title": app_title,
                "novel": prepared_novel,
                "chapters": display_chapters,
                "display_chapters": display_chapters,
                "hidden_subscriber_count": hidden_subscriber_count,
                "fox": fox,
                "viewer": public_viewer(viewer),
                "access_profile": access_profile,
            },
        )

    @router.get("/chapter/{chapter_id}")
    async def chapter_page(request: Request, chapter_id: str):
        viewer = viewer_from_request(request)
        viewer_role = str(viewer.get("role") or "guest")
        chapter = get_chapter_by_id(chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Глава не найдена")
        novel = get_novel_by_id(clean_value(chapter.get("novel_id")))
        if not novel:
            raise HTTPException(status_code=404, detail="Новелла главы не найдена")
        viewer_role, access_profile = effective_role_for_novel(viewer, novel)
        if not can_view_novel_for_profile(novel, access_profile):
            raise HTTPException(status_code=403, detail="Эта новелла доступна подписчикам")
        if not to_bool(novel.get("is_visible"), True) and viewer_role != "keeper":
            raise HTTPException(status_code=404, detail="Глава не найдена")

        all_chapters = get_novel_chapters(clean_value(novel.get("id")))
        prepared_chapter = prepare_chapter_for_template(chapter, viewer_role)
        prepared_novel = prepare_novel_for_template(novel)
        prepared_novel["required_role"] = novel_required_role(novel)
        previous_chapter, next_chapter = get_neighbor_chapters_for_access(
            all_chapters, clean_value(prepared_chapter.get("chapter_id")), novel, access_profile
        )
        index_info = get_chapter_index_info_for_access(
            all_chapters, clean_value(prepared_chapter.get("chapter_id")), novel, access_profile
        )
        access_decision = decide_chapter_access(chapter, novel, access_profile)
        url = access_decision.url
        is_locked = not access_decision.allowed
        telegraph_content = None
        telegraph_error = ""
        preview_text = ""

        if url:
            telegraph_content, telegraph_error = fetch_telegraph_content(url)
        else:
            preview_text, preview_error = fetch_locked_preview(chapter)
            telegraph_error = preview_error if not preview_text else ""

        required_role = normalize_required_role(chapter.get("access_level"))
        fox = get_fox()
        return templates.TemplateResponse(
            request,
            "chapter.html",
            {
                "app_title": app_title,
                "chapter": prepared_chapter,
                "novel": prepared_novel,
                "previous_chapter": previous_chapter,
                "next_chapter": next_chapter,
                "chapter_index": index_info["chapter_index"],
                "available_chapters": index_info["available_chapters"],
                "is_locked": is_locked,
                "telegraph_content": telegraph_content,
                "telegraph_error": telegraph_error,
                "preview_text": preview_text,
                "required_role": required_role,
                "access_copy": access_copy(required_role),
                "boosty_access_url": clean_value(novel.get("boosty_premium_url")) or clean_value(novel.get("boosty_url")),
                "tribute_access_url": TRIBUTE_KEEPER_URL,
                "fox": fox,
                "viewer": public_viewer(viewer),
                "access_profile": access_profile,
                "access_decision": access_decision.to_dict(),
            },
        )

    @router.get("/api/fox")
    async def api_fox():
        fox = get_fox()
        return {"status": "ok", "fox": fox}

    @router.get("/api/library")
    async def api_library(request: Request):
        viewer = viewer_from_request(request)
        viewer_role = str(viewer.get("role") or "guest")
        novels = get_all_novels(include_hidden=viewer_role == "keeper")
        chapters = get_all_chapters()
        prepared_novels = prepare_library_novels_for_access(novels, chapters, viewer)
        return {
            "status": "ok",
            "viewer": public_viewer(viewer),
            "novels_count": len(prepared_novels),
            "chapters_count": len(chapters),
            "novels_sample": prepared_novels,
        }

    @router.get("/api/novel/{slug}")
    async def api_novel(request: Request, slug: str):
        viewer = viewer_from_request(request)
        viewer_role = str(viewer.get("role") or "guest")
        novel = get_novel_by_slug(slug, include_hidden=viewer_role == "keeper")
        if not novel:
            raise HTTPException(status_code=404, detail="Новелла не найдена")
        viewer_role, access_profile = effective_role_for_novel(viewer, novel)
        if not can_view_novel_for_profile(novel, access_profile):
            raise HTTPException(status_code=403, detail="Эта новелла доступна подписчикам")
        all_chapters = get_novel_chapters(clean_value(novel.get("id")))
        prepared_novel = prepare_novel_for_template(novel)
        display_chapters, hidden_subscriber_count = build_chapter_display_list_for_access(
            all_chapters, novel, access_profile
        )
        return {
            "status": "ok",
            "viewer": public_viewer(viewer),
            "novel": prepared_novel,
            "chapters": display_chapters,
            "hidden_subscriber_count": hidden_subscriber_count,
            "access_profile": access_profile,
        }

    return router
