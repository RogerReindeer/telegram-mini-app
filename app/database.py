"""Supabase/PostgREST access layer.

All direct HTTP work with Supabase lives here. Application routes and services
should use these helpers instead of reading SUPABASE_* variables or calling
requests directly. The module keeps the existing synchronous behavior, but the
boundary is now small enough to replace with httpx.AsyncClient later.
"""

from __future__ import annotations

from typing import Any

import requests

from .config import settings


class SupabaseError(RuntimeError):
    """Raised when Supabase/PostgREST returns an error response."""


class SupabaseClient:
    def __init__(self, url: str, service_key: str, timeout_seconds: int = 30) -> None:
        self.url = (url or "").rstrip("/")
        self.service_key = service_key or ""
        self.timeout_seconds = max(1, int(timeout_seconds or 30))

    def ready(self) -> bool:
        return bool(self.url and self.service_key)

    def headers(self, prefer: str | None = None, range_header: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        if range_header:
            headers["Range-Unit"] = "items"
            headers["Range"] = range_header
        return headers

    def request(
        self,
        method: str,
        table: str,
        params: dict[str, Any] | None = None,
        payload: Any | None = None,
        prefer: str | None = None,
        range_header: str | None = None,
    ) -> Any:
        if not self.ready():
            raise SupabaseError("Supabase env vars are not configured")

        response = requests.request(
            method=method,
            url=f"{self.url}/rest/v1/{table}",
            headers=self.headers(prefer=prefer, range_header=range_header),
            params=params or {},
            json=payload,
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise SupabaseError(f"Supabase error {response.status_code}: {response.text}")
        if not response.text:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def select(
        self,
        table: str,
        select: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"select": select}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit:
            params["limit"] = limit
            result = self.request("GET", table, params=params)
            return result if isinstance(result, list) else []

        # PostgREST commonly caps responses at 1000 rows. Page explicitly.
        all_rows: list[dict] = []
        offset = 0
        page_size = 1000
        while True:
            result = self.request(
                "GET",
                table,
                params=params,
                range_header=f"{offset}-{offset + page_size - 1}",
            )
            if not isinstance(result, list) or not result:
                break
            all_rows.extend(result)
            if len(result) < page_size:
                break
            offset += page_size
        return all_rows


    def _strip_private_sync_keys(self, row: dict[str, Any]) -> dict[str, Any]:
        """Remove spreadsheet-only diagnostics metadata before sending to Supabase."""
        return {key: value for key, value in row.items() if not str(key).startswith("__")}

    def _row_label_for_error(self, row: dict[str, Any], fallback_index: int) -> str:
        """Return a safe spreadsheet-like row label for upsert diagnostics."""
        sheet_name = str(row.get("__sheet_name") or row.get("sheet_name") or "").strip()
        row_number = str(row.get("__row_number") or row.get("row_number") or "").strip()
        parts: list[str] = []
        if sheet_name and row_number:
            parts.append(f"{sheet_name}!{row_number}")
        elif row_number:
            parts.append(f"row {row_number}")
        else:
            parts.append(f"batch row {fallback_index}")

        for key in ("chapter_id", "novel_id", "code", "name"):
            value = row.get(key)
            if value is not None and str(value).strip():
                parts.append(f"{key}={str(value).strip()[:80]}")
        return ", ".join(parts)

    def _diagnose_failed_upsert_batch(
        self,
        table: str,
        batch: list[dict],
        conflict_key: str,
        absolute_start: int,
        max_failures: int = 5,
    ) -> str:
        """Retry a failed batch row-by-row to identify bad rows.

        This runs only after Supabase rejected a whole batch. It makes production
        sync errors actionable: instead of “batch 8 failed”, the response points
        to the specific ChapterID / spreadsheet row that Supabase rejected.
        """
        failures: list[str] = []
        for offset, row in enumerate(batch, start=1):
            try:
                self.request(
                    "POST",
                    table,
                    params={"on_conflict": conflict_key},
                    payload=[self._strip_private_sync_keys(row)],
                    prefer="resolution=merge-duplicates,return=minimal",
                )
            except Exception as error:  # pragma: no cover - exercised by runtime tests with a fake client
                absolute_row = absolute_start + offset
                label = self._row_label_for_error(row, absolute_row)
                failures.append(f"{label}: {error}")
                if len(failures) >= max_failures:
                    break
        if not failures:
            return "Не удалось выделить отдельную строку: возможно, ошибка зависит от сочетания строк в пакете."
        suffix = "" if len(failures) < max_failures else " Остальные ошибки не показаны."
        return "Проблемные строки: " + " | ".join(failures) + suffix

    def upsert(
        self,
        table: str,
        rows: list[dict],
        conflict_key: str,
        batch_size: int = 100,
    ) -> int:
        if not rows:
            return 0

        safe_batch_size = max(1, min(int(batch_size or 100), 250))
        submitted = 0

        for start in range(0, len(rows), safe_batch_size):
            batch = rows[start:start + safe_batch_size]
            batch_number = start // safe_batch_size + 1
            try:
                self.request(
                    "POST",
                    table,
                    params={"on_conflict": conflict_key},
                    payload=[self._strip_private_sync_keys(row) for row in batch],
                    prefer="resolution=merge-duplicates,return=minimal",
                )
            except Exception as error:
                diagnostics = self._diagnose_failed_upsert_batch(
                    table=table,
                    batch=batch,
                    conflict_key=conflict_key,
                    absolute_start=start,
                )
                raise SupabaseError(
                    f"Ошибка Supabase: таблица {table}, пакет {batch_number}, "
                    f"строки {start + 1}-{start + len(batch)}. {error}. {diagnostics}"
                ) from error
            submitted += len(batch)

        return submitted


supabase = SupabaseClient(
    url=settings.supabase_url,
    service_key=settings.supabase_service_key,
    timeout_seconds=30,
)


def supabase_ready() -> bool:
    return supabase.ready()


def supabase_request(
    method: str,
    table: str,
    params: dict[str, Any] | None = None,
    payload: Any | None = None,
    prefer: str | None = None,
    range_header: str | None = None,
) -> Any:
    return supabase.request(
        method=method,
        table=table,
        params=params,
        payload=payload,
        prefer=prefer,
        range_header=range_header,
    )


def db_select(
    table: str,
    select: str = "*",
    filters: dict[str, str] | None = None,
    order: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    return supabase.select(table, select=select, filters=filters, order=order, limit=limit)


def db_upsert(table: str, rows: list[dict], conflict_key: str, batch_size: int = 100) -> int:
    return supabase.upsert(table, rows, conflict_key, batch_size=batch_size)


def db_insert(table: str, row: dict[str, Any], prefer: str = "return=representation") -> list[dict]:
    result = supabase.request("POST", table, payload=row, prefer=prefer)
    return result if isinstance(result, list) else []


def db_update(table: str, filters: dict[str, str], patch: dict[str, Any], prefer: str = "return=minimal") -> Any:
    return supabase.request("PATCH", table, params=filters, payload=patch, prefer=prefer)


def db_delete(table: str, filters: dict[str, str], prefer: str = "return=minimal") -> Any:
    return supabase.request("DELETE", table, params=filters, prefer=prefer)
