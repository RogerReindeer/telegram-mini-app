from __future__ import annotations

from typing import Any
import requests
from .config import settings

TIMEOUT = 12


def is_configured() -> bool:
    return settings.supabase_configured


def _headers(prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def table_url(table: str) -> str:
    return settings.supabase_url.rstrip("/") + f"/rest/v1/{table}"


def select(table: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not is_configured():
        return []
    response = requests.get(table_url(table), headers=_headers(), params=params or {"select": "*"}, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


def upsert(table: str, rows: list[dict[str, Any]], on_conflict: str | None = None) -> dict[str, Any]:
    if not is_configured():
        return {"skipped": True, "reason": "supabase_not_configured", "rows": len(rows)}
    params = {"on_conflict": on_conflict} if on_conflict else None
    response = requests.post(table_url(table), headers=_headers("resolution=merge-duplicates"), params=params, json=rows, timeout=TIMEOUT)
    response.raise_for_status()
    return {"ok": True, "rows": len(rows), "status_code": response.status_code}


def insert(table: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not is_configured():
        return {"skipped": True, "reason": "supabase_not_configured", "rows": len(rows)}
    response = requests.post(table_url(table), headers=_headers(), json=rows, timeout=TIMEOUT)
    response.raise_for_status()
    return {"ok": True, "rows": len(rows), "status_code": response.status_code}
