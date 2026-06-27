"""Small in-memory TTL cache for read-heavy MiniApp data.

The cache is intentionally process-local. It is enough for the current Render
single-instance deployment and keeps the code free from an extra Redis service.
Every value is deep-copied on get/set so route handlers cannot accidentally
mutate cached shared state.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Any

from .config import settings


@dataclass(slots=True)
class CacheEntry:
    value: Any
    expires_at: float
    namespace: str


class TTLCache:
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry] = {}
        self._lock = RLock()

    def get(self, key: str) -> Any | None:
        now = monotonic()
        with self._lock:
            entry = self._items.get(key)
            if not entry:
                return None
            if entry.expires_at <= now:
                self._items.pop(key, None)
                return None
            return deepcopy(entry.value)

    def set(self, key: str, value: Any, ttl_seconds: int | float, namespace: str = "default") -> Any:
        ttl = max(0, float(ttl_seconds or 0))
        if ttl <= 0:
            return deepcopy(value)
        with self._lock:
            self._items[key] = CacheEntry(
                value=deepcopy(value),
                expires_at=monotonic() + ttl,
                namespace=namespace,
            )
        return deepcopy(value)

    def get_or_set(self, key: str, ttl_seconds: int | float, factory, namespace: str = "default") -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        return self.set(key, value, ttl_seconds=ttl_seconds, namespace=namespace)

    def clear(self, namespace: str | None = None) -> int:
        with self._lock:
            if namespace is None:
                count = len(self._items)
                self._items.clear()
                return count
            keys = [key for key, entry in self._items.items() if entry.namespace == namespace]
            for key in keys:
                self._items.pop(key, None)
            return len(keys)

    def stats(self) -> dict[str, Any]:
        now = monotonic()
        with self._lock:
            namespaces: dict[str, int] = {}
            expired = 0
            for entry in self._items.values():
                if entry.expires_at <= now:
                    expired += 1
                namespaces[entry.namespace] = namespaces.get(entry.namespace, 0) + 1
            return {
                "items": len(self._items),
                "expired": expired,
                "namespaces": namespaces,
            }


app_cache = TTLCache()


def cache_get_or_set(key: str, ttl_seconds: int | float, factory, namespace: str = "default") -> Any:
    return app_cache.get_or_set(key, ttl_seconds, factory, namespace=namespace)


def clear_catalog_cache() -> int:
    return app_cache.clear("catalog")


def clear_telegraph_cache() -> int:
    return app_cache.clear("telegraph")


def clear_image_cache() -> int:
    return app_cache.clear("images")


def clear_all_caches() -> int:
    return app_cache.clear()


def cache_stats() -> dict[str, Any]:
    return app_cache.stats()


def catalog_cache_ttl() -> int:
    return settings.catalog_cache_seconds


def telegraph_cache_ttl() -> int:
    return settings.telegraph_cache_seconds


def image_cache_ttl() -> int:
    return settings.image_cache_seconds
