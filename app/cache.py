from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

@dataclass
class CacheItem:
    value: Any
    expires_at: float

_cache: dict[str, CacheItem] = {}

def get(key: str) -> Any | None:
    item = _cache.get(key)
    if not item:
        return None
    if item.expires_at < time.time():
        _cache.pop(key, None)
        return None
    return item.value


def set(key: str, value: Any, ttl_seconds: int = 60) -> Any:
    _cache[key] = CacheItem(value=value, expires_at=time.time() + ttl_seconds)
    return value


def clear(prefix: str | None = None) -> int:
    if prefix is None:
        count = len(_cache)
        _cache.clear()
        return count
    keys = [key for key in _cache if key.startswith(prefix)]
    for key in keys:
        _cache.pop(key, None)
    return len(keys)


def stats() -> dict[str, Any]:
    return {"items": len(_cache), "keys": sorted(_cache.keys())[:50]}
