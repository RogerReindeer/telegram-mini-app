"""In-memory operational metrics for owner diagnostics.

The metrics are intentionally aggregate-only: no tokens, initData, chapter text,
raw request bodies, or personal profile details are stored here.
"""

from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

MAX_RECENT_EVENTS = 50

_lock = Lock()
_counters: Counter[str] = Counter()
_recent_events: deque[dict[str, Any]] = deque(maxlen=MAX_RECENT_EVENTS)
_started_at = datetime.now(timezone.utc).isoformat()


def increment_metric(name: str, amount: int = 1) -> None:
    key = str(name or "unknown").strip() or "unknown"
    with _lock:
        _counters[key] += int(amount or 1)


def record_metric_event(name: str, *, status: str = "ok", details: dict[str, Any] | None = None) -> None:
    key = str(name or "unknown").strip() or "unknown"
    safe_details = sanitize_event_details(details or {})
    event = {
        "name": key,
        "status": str(status or "ok"),
        "details": safe_details,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        _counters[key] += 1
        _counters[f"{key}.{event['status']}"] += 1
        _recent_events.appendleft(event)


def sanitize_event_details(details: dict[str, Any]) -> dict[str, Any]:
    blocked = {"token", "authorization", "cookie", "initdata", "init_data", "body", "payload", "secret"}
    result: dict[str, Any] = {}
    for key, value in (details or {}).items():
        normalized_key = str(key).lower()
        if any(word in normalized_key for word in blocked):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            text = str(value) if value is not None else ""
            result[str(key)] = text[:200] if isinstance(value, str) else value
        elif isinstance(value, (list, tuple, set)):
            result[str(key)] = len(value)
        elif isinstance(value, dict):
            result[str(key)] = {"keys": len(value)}
        else:
            result[str(key)] = str(type(value).__name__)
    return result


def metrics_snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "status": "ok",
            "started_at": _started_at,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "counters": dict(sorted(_counters.items())),
            "recent_events": list(_recent_events),
        }


def reset_metrics() -> dict[str, Any]:
    with _lock:
        count = sum(_counters.values())
        _counters.clear()
        _recent_events.clear()
    return {"status": "ok", "cleared_events": count}
