"""Safe operational event logging.

Logs are written to stdout for Render and mirrored to in-memory aggregate metrics.
Never pass secrets or raw user payloads into record_event().
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..config import settings
from .metrics import record_metric_event, sanitize_event_details


def record_event(name: str, *, status: str = "ok", **details: Any) -> None:
    safe_details = sanitize_event_details(details)
    if settings.app_metrics_enabled:
        record_metric_event(name, status=status, details=safe_details)
    event = {"name": str(name or "unknown"), "status": str(status or "ok"), "details": safe_details, "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        _RECENT_EVENTS.append(event)
        del _RECENT_EVENTS[:-100]
    except NameError:
        pass
    if not settings.app_events_enabled:
        return
    line = {
        "type": "app_event",
        "name": str(name or "unknown"),
        "status": str(status or "ok"),
        "details": safe_details,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(line, ensure_ascii=False, sort_keys=True))

_RECENT_EVENTS: list[dict[str, Any]] = []


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent in-memory operational events without secrets."""
    return list(_RECENT_EVENTS[-max(1, int(limit or 50)):])
