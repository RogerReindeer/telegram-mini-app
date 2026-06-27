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
                    payload=batch,
                    prefer="resolution=merge-duplicates,return=minimal",
                )
            except Exception as error:
                raise SupabaseError(
                    f"Ошибка Supabase: таблица {table}, пакет {batch_number}, "
                    f"строки {start + 1}-{start + len(batch)}. {error}"
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
