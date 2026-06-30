from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / 'static'


@lru_cache(maxsize=64)
def asset_hash(filename: str) -> str:
    path = STATIC_DIR / filename
    if not path.exists():
        return 'missing'
    return sha256(path.read_bytes()).hexdigest()[:12]


def static_url(filename: str) -> str:
    return f'/static/{filename}?v={asset_hash(filename)}'


def manifest() -> dict[str, str]:
    return {name: asset_hash(name) for name in ('style.css', 'settings.js')}
