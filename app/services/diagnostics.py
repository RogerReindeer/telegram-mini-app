"""Operational diagnostics for MiniApp content and deployment.

This module is intentionally read-only. It helps the owner catch spreadsheet
mistakes before readers see broken cards or locked chapters with confusing
states. Routers should expose these reports only behind the admin/sync token.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from ..cache import cache_stats
from ..database import db_select, supabase_ready
from .catalog import adapt_chapter_from_db, adapt_novel_from_db, get_all_chapters, get_all_novels, get_fox
from .sync import parse_date
from ..utils import effective_part_no_for_chapter_id, expected_chapter_id

ALLOWED_CONTENT_HOSTS = {
    "telegra.ph",
    "graph.org",
    "teletype.in",
}

Problem = dict[str, Any]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _clean(value).lower()
    return text in {"1", "true", "yes", "y", "да", "visible", "show", "✅", "✓"}


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _is_url(value: Any) -> bool:
    text = _clean(value)
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _content_host(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    return urlparse(text).netloc.lower().removeprefix("www.")


def _add_problem(
    problems: list[Problem],
    *,
    severity: str,
    code: str,
    message: str,
    novel_id: Any | None = None,
    chapter_id: Any | None = None,
    field: str | None = None,
) -> None:
    problems.append({
        "severity": severity,
        "code": code,
        "message": message,
        "novel_id": novel_id,
        "chapter_id": chapter_id,
        "field": field,
    })


def _public_sync_run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sync_id": row.get("sync_id") or row.get("id"),
        "status": row.get("status"),
        "source": row.get("source"),
        "schema_version": row.get("schema_version"),
        "novels_received": row.get("novels_received"),
        "chapters_received": row.get("chapters_received"),
        "warnings_count": row.get("warnings_count"),
        "error_message": row.get("error_message"),
        "started_at": row.get("started_at") or row.get("created_at"),
        "finished_at": row.get("finished_at") or row.get("updated_at"),
    }


def _latest_sync_runs(limit: int = 5) -> list[dict[str, Any]]:
    if not supabase_ready():
        return []
    try:
        rows = db_select("sync_runs", order="started_at.desc", limit=max(1, min(limit, 20)))
    except Exception:
        return []
    return [_public_sync_run(row) for row in rows]


def build_content_audit() -> dict[str, Any]:
    """Return a safe, owner-facing report about catalog/chapter data quality."""
    novels = get_all_novels()
    chapters = get_all_chapters()
    fox = get_fox() or {}
    today = _today_iso()

    problems: list[Problem] = []
    chapters_by_novel: dict[int, list[dict[str, Any]]] = defaultdict(list)
    visible_novel_ids: set[int] = set()

    for novel in novels:
        novel_id = int(novel.get("novel_id") or novel.get("id") or 0)
        if novel_id:
            if _is_truthy(novel.get("miniapp_visible", True)):
                visible_novel_ids.add(novel_id)

    for chapter in chapters:
        novel_id = int(chapter.get("novel_id") or 0)
        if novel_id:
            chapters_by_novel[novel_id].append(chapter)

    code_counts = Counter(_clean(novel.get("code") or novel.get("slug")).casefold() for novel in novels if _clean(novel.get("code") or novel.get("slug")))
    title_counts = Counter(_clean(novel.get("title_ru") or novel.get("title")).casefold() for novel in novels if _clean(novel.get("title_ru") or novel.get("title")))

    for novel in novels:
        novel_id = int(novel.get("novel_id") or novel.get("id") or 0)
        visible = _is_truthy(novel.get("miniapp_visible", True))
        code = _clean(novel.get("code") or novel.get("slug"))
        title = _clean(novel.get("title_ru") or novel.get("title") or novel.get("novel_short"))
        cover_url = _clean(novel.get("cover_url"))

        if not novel_id:
            _add_problem(problems, severity="error", code="novel_missing_id", message="У новеллы нет novel_id.")
        if visible and not code:
            _add_problem(problems, severity="error", code="visible_novel_missing_code", message="Видимая новелла без Code/slug.", novel_id=novel_id, field="code")
        if visible and not title:
            _add_problem(problems, severity="error", code="visible_novel_missing_title", message="Видимая новелла без названия.", novel_id=novel_id, field="title_ru")
        if code and code_counts[code.casefold()] > 1:
            _add_problem(problems, severity="error", code="duplicate_novel_code", message=f"Повторяется Code/slug: {code}.", novel_id=novel_id, field="code")
        if title and title_counts[title.casefold()] > 1:
            _add_problem(problems, severity="warning", code="duplicate_novel_title", message=f"Повторяется русское название: {title}.", novel_id=novel_id, field="title_ru")
        if visible and not chapters_by_novel.get(novel_id):
            _add_problem(problems, severity="warning", code="visible_novel_without_chapters", message="Видимая новелла без глав в MiniApp.", novel_id=novel_id)
        if cover_url and not _is_url(cover_url):
            _add_problem(problems, severity="warning", code="bad_cover_url", message="CoverURL не похож на http/https URL.", novel_id=novel_id, field="cover_url")

    chapter_ids = Counter(_clean(chapter.get("chapter_id")) for chapter in chapters if _clean(chapter.get("chapter_id")))
    for chapter in chapters:
        chapter_id = _clean(chapter.get("chapter_id"))
        novel_id = int(chapter.get("novel_id") or 0)
        chapter_no = int(chapter.get("chapter_no") or 0)
        source_chapter_no = _clean(chapter.get("source_chapter_no")) or str(chapter_no or "")
        part_no = effective_part_no_for_chapter_id(chapter_id, chapter.get("part_no"))
        expected_id = expected_chapter_id(novel_id, source_chapter_no, part_no) if novel_id and chapter_no >= 0 else ""
        translation_date = parse_date(chapter.get("translation_date"))
        free_date = parse_date(chapter.get("free_release_date"))
        premium_date = parse_date(chapter.get("premium_release_date"))
        free_url = _clean(chapter.get("telegraph_free_url"))
        premium_url = _clean(chapter.get("telegraph_premium_url"))
        has_any_url = bool(free_url or premium_url)

        if not chapter_id:
            _add_problem(problems, severity="error", code="chapter_missing_id", message="Глава без chapter_id.", novel_id=novel_id)
            continue
        if chapter_ids[chapter_id] > 1:
            _add_problem(problems, severity="error", code="duplicate_chapter_id", message=f"Повторяется ChapterID: {chapter_id}.", novel_id=novel_id, chapter_id=chapter_id, field="chapter_id")
        if expected_id and chapter_id != expected_id:
            _add_problem(problems, severity="error", code="chapter_id_mismatch", message=f"ChapterID должен быть {expected_id}. Для частей используйте NovelID-SourceChapterNo-PartNo, например 2-52-1.", novel_id=novel_id, chapter_id=chapter_id, field="chapter_id")
        if novel_id not in visible_novel_ids and novel_id not in chapters_by_novel:
            _add_problem(problems, severity="warning", code="chapter_without_known_novel", message="Глава ссылается на неизвестную новеллу.", novel_id=novel_id, chapter_id=chapter_id)
        if has_any_url and not translation_date:
            _add_problem(problems, severity="warning", code="url_without_translation_date", message="Есть Telegraph/Teletype URL, но нет TranslationDate.", novel_id=novel_id, chapter_id=chapter_id, field="translation_date")
        if free_date and not free_url:
            _add_problem(problems, severity="warning", code="free_date_without_free_url", message="Есть FreeReleaseDate, но нет TelegraphFreeURL.", novel_id=novel_id, chapter_id=chapter_id, field="telegraph_free_url")
        if premium_date and not premium_url and not free_url:
            _add_problem(problems, severity="warning", code="premium_date_without_content_url", message="Есть PremiumReleaseDate, но нет URL главы.", novel_id=novel_id, chapter_id=chapter_id, field="telegraph_premium_url")
        if free_url and not free_date:
            _add_problem(problems, severity="warning", code="free_url_without_free_date", message="Есть TelegraphFreeURL, но нет FreeReleaseDate.", novel_id=novel_id, chapter_id=chapter_id, field="free_release_date")
        if premium_url and not premium_date:
            _add_problem(problems, severity="warning", code="premium_url_without_premium_date", message="Есть TelegraphPremiumURL, но нет PremiumReleaseDate.", novel_id=novel_id, chapter_id=chapter_id, field="premium_release_date")
        if free_date and premium_date and free_date < premium_date:
            _add_problem(problems, severity="warning", code="free_before_premium", message="FreeReleaseDate раньше PremiumReleaseDate. Проверь расписание доступа.", novel_id=novel_id, chapter_id=chapter_id)
        for field_name, url in (("telegraph_free_url", free_url), ("telegraph_premium_url", premium_url)):
            if url and not _is_url(url):
                _add_problem(problems, severity="error", code="bad_content_url", message=f"{field_name} не похож на http/https URL.", novel_id=novel_id, chapter_id=chapter_id, field=field_name)
            elif url:
                host = _content_host(url)
                if host and host not in ALLOWED_CONTENT_HOSTS:
                    _add_problem(problems, severity="warning", code="unexpected_content_host", message=f"Неожиданный домен контента: {host}.", novel_id=novel_id, chapter_id=chapter_id, field=field_name)
        if translation_date and translation_date > today:
            _add_problem(problems, severity="info", code="future_translation_date", message="TranslationDate стоит в будущем.", novel_id=novel_id, chapter_id=chapter_id, field="translation_date")

    severity_counts = Counter(problem["severity"] for problem in problems)
    problem_counts = Counter(problem["code"] for problem in problems)
    problems_by_severity = {
        "critical": [problem for problem in problems if problem.get("severity") == "error"],
        "warning": [problem for problem in problems if problem.get("severity") == "warning"],
        "info": [problem for problem in problems if problem.get("severity") == "info"],
    }
    launch_blockers = problems_by_severity["critical"]
    return {
        "status": "blocked" if launch_blockers else "attention" if severity_counts.get("warning") else "ok",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "novels": len(novels),
            "visible_novels": len(visible_novel_ids),
            "chapters": len(chapters),
            "fox": len(fox),
            "errors": severity_counts.get("error", 0),
            "warnings": severity_counts.get("warning", 0),
            "info": severity_counts.get("info", 0),
            "launch_blockers": len(launch_blockers),
        },
        "problem_codes": dict(sorted(problem_counts.items())),
        "problems_by_severity": {
            "critical": problems_by_severity["critical"][:100],
            "warning": problems_by_severity["warning"][:200],
            "info": problems_by_severity["info"][:200],
        },
        "problems": problems[:500],
        "truncated": len(problems) > 500,
        "latest_sync_runs": _latest_sync_runs(5),
        "cache": cache_stats(),
    }


def build_catalog_export() -> dict[str, Any]:
    """Build a safe JSON snapshot of read-only catalog data for backup/debug."""
    novels = [adapt_novel_from_db(row) for row in get_all_novels()]
    chapters = [adapt_chapter_from_db(row) for row in get_all_chapters()]
    fox = get_fox() or {}
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": "miniapp_supabase_readonly",
        "schema": "catalog_export_v1",
        "counts": {
            "novels": len(novels),
            "chapters": len(chapters),
            "fox": len(fox),
        },
        "novels": novels,
        "chapters": chapters,
        "fox": fox,
    }
