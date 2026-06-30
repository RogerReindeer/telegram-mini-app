from __future__ import annotations

from typing import Any

def handle_tribute_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "disabled": True, "reason": "Tribute is temporarily disabled in current product plan"}

def import_boosty_order(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "accepted": True, "source": "boosty", "payload_keys": sorted(payload.keys())}
