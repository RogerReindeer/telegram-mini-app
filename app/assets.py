from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from .config import settings

SITE_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = SITE_ROOT / "static"


@lru_cache(maxsize=256)
def static_asset_version(asset_path: str) -> str:
    """Return a short content hash for a file in /static.

    The hash is calculated once per process.  On Render a new deploy starts a new
    process, so changed CSS/JS files automatically receive a new URL and bypass
    stale Telegram WebView cache.
    """
    safe_path = _normalize_static_path(asset_path)
    file_path = (STATIC_ROOT / safe_path).resolve()
    try:
        if not file_path.is_file() or STATIC_ROOT.resolve() not in file_path.parents:
            return settings.app_version
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        return digest[:12]
    except OSError:
        return settings.app_version


def static_url(asset_path: str) -> str:
    """Build a cache-busted URL for a static file.

    Example: ``/static/style.css?v=abc123``.  The query string is enough for
    browser/WebView cache invalidation while keeping FastAPI StaticFiles simple.
    """
    safe_path = _normalize_static_path(asset_path)
    encoded = "/".join(quote(part) for part in safe_path.split("/"))
    return f"/static/{encoded}?v={static_asset_version(safe_path)}"


def static_manifest() -> dict[str, str]:
    """Small diagnostics map for /version without exposing local paths."""
    return {
        "style.css": static_asset_version("style.css"),
        "settings.js": static_asset_version("settings.js"),
    }


def _normalize_static_path(asset_path: str) -> str:
    text = str(asset_path or "").strip().replace("\\", "/")
    text = text.lstrip("/")
    if text.startswith("static/"):
        text = text[len("static/") :]
    parts = [part for part in text.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        return ""
    return "/".join(parts)
