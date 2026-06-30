from __future__ import annotations

from typing import Any
from ..config import settings
from ..assets import manifest
from .catalog import list_novels, list_chapters, get_fox


def project_state() -> dict[str, Any]:
    novels = list_novels()
    chapters_count = sum(len(list_chapters(novel["id"])) for novel in novels)
    return {
        "app_version": settings.app_version,
        "supabase_configured": settings.supabase_configured,
        "telegram_bot_configured": settings.telegram_bot_configured,
        "sync_token_configured": bool(settings.sync_token),
        "novels_count": len(novels),
        "chapters_count": chapters_count,
        "assets": manifest(),
    }


def content_audit() -> dict[str, Any]:
    issues = []
    for novel in list_novels():
        if not novel.get("display_title"):
            issues.append({"severity": "error", "message": f"Novel {novel.get('id')} has empty title"})
        for chapter in list_chapters(novel["id"]):
            if not chapter.get("chapter_id"):
                issues.append({"severity": "error", "message": f"Novel {novel.get('id')} has chapter without ChapterID"})
            if not chapter.get("display_title"):
                issues.append({"severity": "warning", "message": f"Chapter {chapter.get('chapter_id')} has empty title"})
    return {"ok": not any(i["severity"] == "error" for i in issues), "issues": issues}


def production_check() -> dict[str, Any]:
    blockers = []
    warnings = []
    if not settings.sync_token:
        blockers.append("SYNC_TOKEN is not configured")
    if not settings.session_secret or settings.session_secret == "change-me":
        warnings.append("SESSION_SECRET uses default value")
    if not settings.supabase_configured:
        warnings.append("Supabase is not configured; app uses local fallback data")
    audit = content_audit()
    if not audit["ok"]:
        blockers.append("Content audit has errors")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "content_audit": audit, "state": project_state()}
