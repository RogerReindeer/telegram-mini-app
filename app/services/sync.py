from __future__ import annotations

from typing import Any
from .. import database
from ..contracts import NOVELS_TABLE, CHAPTERS_TABLE, FOX_TABLE
from ..cache import clear
from ..utils import clean_value


def normalize_payload(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "novels": list(payload.get("novels") or []),
        "chapters": list(payload.get("chapters") or []),
        "fox": list(payload.get("fox") or []),
    }


def validate_chapter_id(row: dict[str, Any]) -> list[str]:
    chapter_id = clean_value(row.get("chapter_id") or row.get("ChapterID"))
    novel_id = clean_value(row.get("novel_id") or row.get("NovelID"))
    chapter_no = clean_value(row.get("chapter_no") or row.get("ChapterNo"))
    source_no = clean_value(row.get("source_chapter_no") or row.get("SourceChapterNo"))
    part_no = clean_value(row.get("part_no") or row.get("PartNo"))
    errors: list[str] = []
    parts = chapter_id.split("-") if chapter_id else []
    if not chapter_id:
        return ["ChapterID is empty"]
    if not novel_id or parts[0] != novel_id:
        errors.append(f"ChapterID {chapter_id}: first segment must equal NovelID {novel_id}")
    if len(parts) == 2:
        if parts[1] not in {chapter_no, source_no}:
            errors.append(f"ChapterID {chapter_id}: second segment must equal ChapterNo or SourceChapterNo")
    elif len(parts) == 3:
        if parts[1] != source_no or parts[2] != part_no:
            errors.append(f"ChapterID {chapter_id}: 3-part format must be NovelID-SourceChapterNo-PartNo")
    else:
        errors.append(f"ChapterID {chapter_id}: unsupported format")
    return errors


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_payload(payload)
    issues = []
    seen = set()
    for idx, row in enumerate(normalized["chapters"], start=1):
        cid = clean_value(row.get("chapter_id") or row.get("ChapterID"))
        if cid in seen:
            issues.append({"severity": "error", "row": idx, "field": "ChapterID", "message": f"Duplicate ChapterID {cid}"})
        seen.add(cid)
        for message in validate_chapter_id(row):
            issues.append({"severity": "error", "row": idx, "field": "ChapterID", "message": message})
    return {"ok": not issues, "issues": issues, "counts": {k: len(v) for k, v in normalized.items()}}


def run_sync(payload: dict[str, Any]) -> dict[str, Any]:
    validation = validate_payload(payload)
    if not validation["ok"]:
        return {"ok": False, "validation": validation}
    normalized = normalize_payload(payload)
    result = {
        "novels": database.upsert(NOVELS_TABLE, normalized["novels"], on_conflict="id") if normalized["novels"] else {"rows": 0},
        "chapters": database.upsert(CHAPTERS_TABLE, normalized["chapters"], on_conflict="chapter_id") if normalized["chapters"] else {"rows": 0},
        "fox": database.upsert(FOX_TABLE, normalized["fox"], on_conflict="id") if normalized["fox"] else {"rows": 0},
    }
    clear()
    return {"ok": True, "result": result, "cache_cleared": True}
