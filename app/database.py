from __future__ import annotations

from typing import Any
from urllib.parse import urlencode
import requests

from .config import settings


class DatabaseUnavailable(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.supabase_ready:
        raise DatabaseUnavailable('Supabase is not configured')
    return {
        'apikey': settings.supabase_key,
        'Authorization': f'Bearer {settings.supabase_key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }


def select(table: str, params: dict[str, Any] | None = None, timeout: int = 12) -> list[dict[str, Any]]:
    query = urlencode(params or {}, doseq=True)
    url = f'{settings.supabase_url}/rest/v1/{table}' + (f'?{query}' if query else '')
    response = requests.get(url, headers=_headers(), timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


def upsert(table: str, rows: list[dict[str, Any]], on_conflict: str | None = None, timeout: int = 20) -> list[dict[str, Any]]:
    if not rows:
        return []
    params = f'?on_conflict={on_conflict}' if on_conflict else ''
    url = f'{settings.supabase_url}/rest/v1/{table}{params}'
    response = requests.post(url, headers=_headers(), json=rows, timeout=timeout)
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError:
        return []
    return data if isinstance(data, list) else []
