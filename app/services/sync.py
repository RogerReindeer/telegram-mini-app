"""Service layer for Translation CRM -> MiniApp -> Supabase sync.

This module owns payload validation/normalization and all Supabase writes for
``POST /sync`` and ``POST /api/sync``. Routers should not talk to Supabase
or know spreadsheet column aliases directly.
"""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from ..cache import clear_catalog_cache, clear_image_cache, clear_telegraph_cache
from ..database import db_insert, db_update, db_upsert, supabase_ready
from ..utils import chapter_id_matches_parts, clean_value, is_date_open, normalize_part_no_for_storage, parse_chapter_id, parse_date, to_bool, to_float, to_int, today_iso
from .catalog_shared import (
    CHAPTER_TABLE_COLUMNS,
    FOX_TABLE_COLUMNS,
    KEY_MAP_CHAPTER,
    KEY_MAP_FOX,
    KEY_MAP_NOVEL,
    NOVEL_TABLE_COLUMNS,
    chapter_release_integrity_issues,
    normalize_dict_keys,
    normalize_fox_name,
    normalize_text_list,
    parse_iso_datetime,
)

EXPECTED_SCHEMA_VERSION = 17


def filter_columns(row: dict, allowed_columns: set[str]) -> dict:
    """Keep DB columns plus private sync metadata used only for diagnostics.

    Keys starting with ``__`` are never written to Supabase; database.upsert()
    strips them before HTTP requests. They let production sync errors point back
    to a Google Sheets row, e.g. ``Chapters!722``.
    """
    return {key: value for key, value in row.items() if key in allowed_columns or str(key).startswith("__")}


def attach_private_sync_metadata(target: dict, source: dict) -> dict:
    for key, value in (source or {}).items():
        if str(key).startswith("__"):
            target[str(key)] = value
    return target


def normalize_novel_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_NOVEL)
    novel_id = to_int(row.get("novel_id"), 0)
    code = clean_value(row.get("code")) or str(novel_id)
    title_ru = clean_value(row.get("title_ru"))
    novel_short = clean_value(row.get("novel_short"))

    normalized = {
        "novel_id": novel_id,
        "code": code,
        "novel_short": novel_short or None,
        "title_ru": title_ru or novel_short or code,
        "title_en": clean_value(row.get("title_en")) or None,
        "title_original": clean_value(row.get("title_original")) or None,
        "original_language": clean_value(row.get("original_language")) or None,
        "post_icons": clean_value(row.get("post_icons")) or None,
        "status": clean_value(row.get("status")) or None,
        "access_model": clean_value(row.get("access_model")) or None,
        "schedule_mode": clean_value(row.get("schedule_mode")) or None,
        "early_access_mode": clean_value(row.get("early_access_mode")) or None,
        "release_year": to_int(row.get("release_year"), 0) or None,
        "author_original": clean_value(row.get("author_original")) or None,
        "author_latin": clean_value(row.get("author_latin")) or None,
        "author_cyrillic": clean_value(row.get("author_cyrillic")) or None,
        "author_translated": clean_value(row.get("author_translated")) or None,
        "cover_url": clean_value(row.get("cover_url")) or None,
        "description": clean_value(row.get("description")) or None,
        "top_description": clean_value(row.get("top_description")) or None,
        "bottom_description": clean_value(row.get("bottom_description")) or None,
        "miniapp_tags": normalize_text_list(row.get("miniapp_tags")),
        "tags_tg_catalog": clean_value(row.get("tags_tg_catalog")) or None,
        "tags_app_catalog": normalize_text_list(row.get("tags_app_catalog")),
        "miniapp_visible": to_bool(row.get("miniapp_visible"), True),
        "total_chapters": max(0, to_int(row.get("total_chapters"), 0)),
        "translated_chapters": max(0, to_int(row.get("translated_chapters"), 0)),
        "free_chapters": max(0, to_int(row.get("free_chapters"), 0)),
        "subscriber_chapters": max(0, to_int(row.get("subscriber_chapters"), 0)),
        "keeper_chapters": max(0, to_int(row.get("keeper_chapters"), 0)),
        "early_access_chapters": max(0, to_int(row.get("early_access_chapters"), 0)),
        "progress_percent": max(0.0, min(1.0, to_float(row.get("progress_percent"), 0.0))),
        "source_url_novelupdates": clean_value(row.get("source_url_novelupdates")) or None,
        "source_url_official": clean_value(row.get("source_url_official")) or None,
        "source_chapter_url": clean_value(row.get("source_chapter_url")) or None,
        "telegram_post_url": clean_value(row.get("telegram_post_url")) or None,
        "boosty_url": clean_value(row.get("boosty_url")) or None,
        "boosty_premium_url": clean_value(row.get("boosty_premium_url")) or None,
        "telegraph_catalog_url": clean_value(row.get("telegraph_catalog_url")) or None,
    }
    attach_private_sync_metadata(normalized, row)
    return filter_columns(normalized, NOVEL_TABLE_COLUMNS)


def normalize_chapter_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_CHAPTER)
    chapter_id = clean_value(row.get("chapter_id"))
    novel_id = to_int(row.get("novel_id"), 0)
    chapter_no = to_int(row.get("chapter_no"), 0)
    source_chapter_no = clean_value(row.get("source_chapter_no"))
    if not source_chapter_no and clean_value(row.get("chapter_no")):
        source_chapter_no = str(chapter_no)
    parsed_id = parse_chapter_id(chapter_id)
    part_no = normalize_part_no_for_storage(chapter_id, row.get("part_no"))
    if novel_id <= 0 or chapter_no < 0:
        raise ValueError("novel_id должен быть положительным, а chapter_no должен быть неотрицательным целым числом")
    if not parsed_id or not chapter_id_matches_parts(chapter_id, novel_id, chapter_no, part_no, source_chapter_no):
        raise ValueError(
            f"chapter_id {chapter_id!r} не соответствует NovelID/ChapterNo/SourceChapterNo/PartNo. "
            "ChapterID — это стабильный уникальный ключ строки; он может быть NovelID-ChapterNo "
            "или NovelID-SourceChapterNo-PartNo. Например: 13-0, 31-2, 2-52-1, 2-52-2."
        )

    normalized = {
        "chapter_id": chapter_id,
        "novel_id": novel_id,
        "volume_no": to_int(row.get("volume_no"), 0) if clean_value(row.get("volume_no")) else None,
        "volume_title": clean_value(row.get("volume_title")) or None,
        "chapter_no": chapter_no,
        "source_chapter_no": source_chapter_no or str(chapter_no),
        "part_no": part_no,
        "chapter_title": clean_value(row.get("chapter_title")) or None,
        "planned_translation_date": parse_date(row.get("planned_translation_date")),
        "translation_date": parse_date(row.get("translation_date")),
        "free_release_date": parse_date(row.get("free_release_date")),
        "premium_release_date": parse_date(row.get("premium_release_date")),
        "prepared_platforms": clean_value(row.get("prepared_platforms")) or None,
        "scheduled_platforms": clean_value(row.get("scheduled_platforms")) or None,
        "publishing_platforms": clean_value(row.get("publishing_platforms")) or None,
        "telegraph_premium_url": clean_value(row.get("telegraph_premium_url")) or None,
        "telegraph_premium_code": clean_value(row.get("telegraph_premium_code")) or None,
        "telegraph_free_url": clean_value(row.get("telegraph_free_url")) or None,
        "telegraph_free_code": clean_value(row.get("telegraph_free_code")) or None,
        "qa_status": to_bool(row.get("qa_status"), False),
    }
    attach_private_sync_metadata(normalized, row)
    return filter_columns(normalized, CHAPTER_TABLE_COLUMNS)


def resolve_external_image_url(value: Any) -> str:
    url = clean_value(value)
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://"):
        return "https://" + url[7:]
    return url


def normalize_fox_row(row: dict) -> dict:
    row = normalize_dict_keys(row, KEY_MAP_FOX)
    normalized = {"name": normalize_fox_name(row.get("name")), "url": resolve_external_image_url(row.get("url"))}
    attach_private_sync_metadata(normalized, row)
    return filter_columns(normalized, FOX_TABLE_COLUMNS)


def _coerce_payload_collection(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def source_row_label(row: dict | None, fallback: str) -> str:
    """Return a human spreadsheet label such as Chapters!722 when available."""
    if not isinstance(row, dict):
        return fallback
    sheet_name = clean_value(row.get("__sheet_name"))
    row_number = clean_value(row.get("__row_number"))
    if sheet_name and row_number:
        return f"{sheet_name}!{row_number}"
    if sheet_name:
        return sheet_name
    return fallback


def _append_issue(target: list[dict[str, Any]], *, severity: str, label: str, message: str, code: str = "validation", row: dict | None = None, field: str | None = None) -> None:
    issue = {
        "severity": severity,
        "code": code,
        "label": label,
        "message": message,
        "field": field,
    }
    if isinstance(row, dict):
        for key in ("chapter_id", "ChapterID", "novel_id", "NovelID", "name", "Name"):
            value = clean_value(row.get(key))
            if value:
                issue[key.lower()] = value
    target.append(issue)


def _issue_text(issue: dict[str, Any]) -> str:
    label = clean_value(issue.get("label"))
    message = clean_value(issue.get("message"))
    return f"{label}: {message}" if label else message


def _group_issues(issues: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "errors": [item for item in issues if item.get("severity") == "error"],
        "warnings": [item for item in issues if item.get("severity") == "warning"],
        "info": [item for item in issues if item.get("severity") == "info"],
    }


def validate_sync_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a MiniApp sync payload without writing to Supabase."""
    issue_rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "source": "Translation CRM",
            "schema_version": EXPECTED_SCHEMA_VERSION,
            "novels": [],
            "chapters": [],
            "fox": [],
            "errors": ["Корень JSON должен быть объектом."],
            "warnings": [],
            "issues": [{"severity": "error", "code": "payload_not_object", "label": "payload", "message": "Корень JSON должен быть объектом."}],
        }

    source = clean_value(payload.get("source")) or "Translation CRM"
    schema_version = to_int(payload.get("schema_version"), 0) or EXPECTED_SCHEMA_VERSION

    if schema_version != EXPECTED_SCHEMA_VERSION:
        _append_issue(
            issue_rows,
            severity="error",
            code="schema_version_mismatch",
            label="payload.schema_version",
            message=f"Неподдерживаемая версия схемы: {schema_version}. Ожидается {EXPECTED_SCHEMA_VERSION}.",
            field="schema_version",
        )

    novels_raw = _coerce_payload_collection(payload.get("novels") or payload.get("Novels") or [])
    chapters_raw = _coerce_payload_collection(payload.get("chapters") or payload.get("Chapters") or [])
    fox_raw = _coerce_payload_collection(payload.get("fox") or payload.get("Fox") or [])

    novels: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    fox_rows: list[dict[str, Any]] = []

    seen_novel_ids: set[int] = set()
    seen_chapter_ids: set[str] = set()
    seen_fox_names: set[str] = set()

    for index, raw in enumerate(novels_raw):
        label = source_row_label(raw, f"Novels[{index}]")
        if not isinstance(raw, dict):
            _append_issue(issue_rows, severity="error", code="row_not_object", label=label, message="строка должна быть объектом.")
            continue
        try:
            row = normalize_novel_row(raw)
        except Exception as error:
            _append_issue(issue_rows, severity="error", code="normalization_failed", label=label, message=str(error))
            continue

        novel_id = to_int(row.get("novel_id"), 0)
        if novel_id <= 0:
            _append_issue(issue_rows, severity="error", code="novel_missing_id", label=label, message="отсутствует или некорректен novel_id.", row=row, field="novel_id")
            continue
        if novel_id in seen_novel_ids:
            _append_issue(issue_rows, severity="error", code="duplicate_novel_id", label=label, message=f"повторяется novel_id={novel_id}.", row=row, field="novel_id")
            continue
        if not clean_value(row.get("title_ru")):
            _append_issue(issue_rows, severity="error", code="novel_missing_title", label=label, message="отсутствует title_ru.", row=row, field="title_ru")
            continue
        if not clean_value(row.get("cover_url")):
            warnings.append(f"NovelID {novel_id}: отсутствует обложка.")
        if not clean_value(row.get("description")):
            warnings.append(f"NovelID {novel_id}: отсутствует описание.")
        seen_novel_ids.add(novel_id)
        novels.append(row)

    for index, raw in enumerate(chapters_raw):
        label = source_row_label(raw, f"Chapters[{index}]")
        if not isinstance(raw, dict):
            _append_issue(issue_rows, severity="error", code="row_not_object", label=label, message="строка должна быть объектом.")
            continue
        try:
            row = normalize_chapter_row(raw)
        except Exception as error:
            _append_issue(issue_rows, severity="error", code="normalization_failed", label=label, message=str(error))
            continue

        chapter_id = clean_value(row.get("chapter_id"))
        novel_id = to_int(row.get("novel_id"), 0)

        if not chapter_id:
            _append_issue(issue_rows, severity="error", code="chapter_missing_id", label=label, message="отсутствует chapter_id.", row=row, field="chapter_id")
            continue
        if chapter_id in seen_chapter_ids:
            _append_issue(issue_rows, severity="error", code="duplicate_chapter_id", label=label, message=f"повторяется chapter_id={chapter_id}.", row=row, field="chapter_id")
            continue
        if novel_id not in seen_novel_ids:
            _append_issue(issue_rows, severity="error", code="chapter_unknown_novel", label=label, message=f"NovelID {novel_id} отсутствует среди отправляемых новелл.", row=row, field="novel_id")
            continue

        seen_chapter_ids.add(chapter_id)
        chapters.append(row)

    for index, raw in enumerate(fox_raw):
        label = source_row_label(raw, f"fox[{index}]")
        if not isinstance(raw, dict):
            _append_issue(issue_rows, severity="error", code="row_not_object", label=label, message="строка должна быть объектом.")
            continue
        try:
            row = normalize_fox_row(raw)
        except Exception as error:
            _append_issue(issue_rows, severity="error", code="normalization_failed", label=label, message=str(error))
            continue

        name = clean_value(row.get("name"))
        url = clean_value(row.get("url"))
        if not name or not url:
            _append_issue(issue_rows, severity="error", code="fox_missing_name_or_url", label=label, message="отсутствует name или url.", row=row)
            continue
        if name in seen_fox_names:
            _append_issue(issue_rows, severity="error", code="duplicate_fox_name", label=label, message=f"повторяется name={name}.", row=row, field="name")
            continue
        seen_fox_names.add(name)
        fox_rows.append(row)

    release_warnings = [issue for chapter in chapters for issue in chapter_release_integrity_issues(chapter)]
    warnings.extend(release_warnings)

    # Сохраняем порядок, но убираем полные дубли предупреждений.
    unique_warnings: list[str] = []
    seen_warnings: set[str] = set()
    for warning in warnings:
        key = warning.casefold()
        if key in seen_warnings:
            continue
        seen_warnings.add(key)
        unique_warnings.append(warning)

    errors = [_issue_text(item) for item in issue_rows if item.get("severity") == "error"]
    return {
        "ok": len(errors) == 0,
        "source": source,
        "schema_version": schema_version,
        "novels": novels,
        "chapters": chapters,
        "fox": fox_rows,
        "errors": errors,
        "warnings": unique_warnings,
        "issues": issue_rows + [
            {"severity": "warning", "code": "release_integrity", "label": "release", "message": warning}
            for warning in unique_warnings
        ],
    }


def normalize_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    validation = validate_sync_payload(payload)
    if validation["errors"]:
        raise HTTPException(status_code=400, detail={"errors": validation["errors"][:100]})
    return validation["novels"], validation["chapters"], validation["fox"]


def build_validation_response(payload: dict[str, Any]) -> dict[str, Any]:
    validation = validate_sync_payload(payload)
    grouped = _group_issues(validation.get("issues", []))
    return {
        "status": "ok" if validation["ok"] else "error",
        "mode": "validate",
        "source": validation["source"],
        "schema_version": validation["schema_version"],
        "expected_schema_version": EXPECTED_SCHEMA_VERSION,
        "novels_received": len(validation["novels"]),
        "chapters_received": len(validation["chapters"]),
        "fox_received": len(validation["fox"]),
        "errors_count": len(validation["errors"]),
        "errors": validation["errors"][:100],
        "warnings_count": len(validation["warnings"]),
        "warnings": validation["warnings"][:100],
        "issues_by_severity": {
            "errors": grouped["errors"][:100],
            "warnings": grouped["warnings"][:100],
            "info": grouped["info"][:100],
        },
        "summary": {
            "status": "blocked" if grouped["errors"] else "attention" if grouped["warnings"] else "ok",
            "first_error": _issue_text(grouped["errors"][0]) if grouped["errors"] else "",
            "first_warning": _issue_text(grouped["warnings"][0]) if grouped["warnings"] else "",
        },
        "would_write": False,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_sync_run(source: str, schema_version: int) -> int | None:
    try:
        rows = db_insert(
            "sync_runs",
            {
                "source": source or "Translation CRM",
                "schema_version": schema_version or EXPECTED_SCHEMA_VERSION,
                "status": "running",
                "started_at": _utc_now_iso(),
            },
            prefer="return=representation",
        )
        if rows and isinstance(rows[0], dict):
            return to_int(rows[0].get("sync_id"), 0) or None
    except Exception as error:
        print("Could not create sync_runs row:", error)
    return None


def _finish_sync_run(sync_id: int | None, patch: dict[str, Any]) -> None:
    if not sync_id:
        return
    try:
        payload = dict(patch)
        payload["finished_at"] = _utc_now_iso()
        db_update("sync_runs", {"sync_id": f"eq.{sync_id}"}, payload)
    except Exception as error:
        print("Could not update sync_runs row:", error)


async def run_sync(payload: dict[str, Any]) -> JSONResponse:
    """Normalize sync payload, record sync_runs, and upsert it into Supabase."""
    if not supabase_ready():
        return JSONResponse(
            {
                "status": "error",
                "stage": "configuration",
                "detail": "На Render не настроены SUPABASE_URL и SUPABASE_KEY/SUPABASE_SERVICE_KEY.",
            },
            status_code=500,
        )

    stage = "validation"
    sync_id: int | None = None

    try:
        if not isinstance(payload, dict):
            payload = {}

        validation = validate_sync_payload(payload)
        sync_id = _create_sync_run(validation["source"], validation["schema_version"])

        if validation["errors"]:
            _finish_sync_run(
                sync_id,
                {
                    "status": "error",
                    "novels_count": len(validation["novels"]),
                    "chapters_count": len(validation["chapters"]),
                    "fox_count": len(validation["fox"]),
                    "warnings": validation["warnings"][:100],
                    "error_message": "\n".join(validation["errors"][:30]),
                },
            )
            return JSONResponse(
                {
                    "status": "error",
                    "sync_id": sync_id,
                    "stage": "validation",
                    "errors_count": len(validation["errors"]),
                    "errors": validation["errors"][:100],
                    "warnings_count": len(validation["warnings"]),
                    "warnings": validation["warnings"][:100],
                    "issues_by_severity": _group_issues(validation.get("issues", [])),
                },
                status_code=400,
            )

        novels = validation["novels"]
        chapters = validation["chapters"]
        fox_rows = validation["fox"]
        warnings = validation["warnings"]

        result: dict[str, Any] = {
            "status": "ok",
            "sync_id": sync_id,
            "source": validation["source"],
            "schema_version": validation["schema_version"],
            "novels_received": len(novels),
            "chapters_received": len(chapters),
            "fox_received": len(fox_rows),
            "novels_upserted": 0,
            "chapters_upserted": 0,
            "fox_upserted": 0,
            "warnings_count": len(warnings),
            "warnings": warnings[:100],
        }

        stage = "novels"
        if novels:
            result["novels_upserted"] = db_upsert("novels", novels, "novel_id", batch_size=50)
            _finish_sync_run(sync_id, {"status": "running", "novels_count": result["novels_upserted"], "warnings": warnings[:100]})

        stage = "chapters"
        if chapters:
            result["chapters_upserted"] = db_upsert("chapters", chapters, "chapter_id", batch_size=100)
            _finish_sync_run(sync_id, {"status": "running", "novels_count": result["novels_upserted"], "chapters_count": result["chapters_upserted"], "warnings": warnings[:100]})

        stage = "fox"
        if fox_rows:
            result["fox_upserted"] = db_upsert("fox", fox_rows, "name", batch_size=50)
            _finish_sync_run(sync_id, {"status": "running", "novels_count": result["novels_upserted"], "chapters_count": result["chapters_upserted"], "fox_count": result["fox_upserted"], "warnings": warnings[:100]})

        result["cache_cleared"] = {
            "catalog": clear_catalog_cache(),
            "telegraph": clear_telegraph_cache(),
            "images": clear_image_cache(),
        }

        _finish_sync_run(
            sync_id,
            {
                "status": "ok",
                "novels_count": len(novels),
                "chapters_count": len(chapters),
                "fox_count": len(fox_rows),
                "warnings": warnings[:100],
                "error_message": None,
            },
        )

        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as error:
        print("MiniApp sync failed at stage:", stage)
        traceback.print_exc()
        _finish_sync_run(
            sync_id,
            {
                "status": "error",
                "warnings": [],
                "error_message": f"{stage}: {error}",
            },
        )
        return JSONResponse({"status": "error", "sync_id": sync_id, "stage": stage, "detail": str(error)}, status_code=500)
