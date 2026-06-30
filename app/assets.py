from __future__ import annotations

import hashlib
from pathlib import Path
from .config import BASE_DIR

_static_dir = BASE_DIR / "static"
_manifest: dict[str, str] = {}


def asset_hash(name: str) -> str:
    path = _static_dir / name
    if not path.exists():
        return "missing"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return digest


def build_manifest() -> dict[str, str]:
    global _manifest
    files = ["style.css", "design-polish.css", "settings.js"]
    _manifest = {name: asset_hash(name) for name in files}
    return dict(_manifest)


def static_url(name: str) -> str:
    version = _manifest.get(name) or asset_hash(name)
    return f"/static/{name}?v={version}"


def manifest() -> dict[str, str]:
    return dict(_manifest or build_manifest())
