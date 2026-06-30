from __future__ import annotations

from datetime import date, datetime, timezone
import re
from typing import Any


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def to_int(value: Any, default: int = 0) -> int:
    text = clean_value(value)
    if not text:
        return default
    try:
        return int(float(text.replace(",", ".")))
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean_value(value)
    if not text:
        return default
    try:
        return float(text.replace(",", "."))
    except (TypeError, ValueError):
        return default


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean_value(value).lower() in {"1", "true", "yes", "y", "да", "истина", "on", "✅"}


def parse_date(value: Any) -> date | None:
    text = clean_value(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def today_iso() -> str:
    return utc_now().date().isoformat()


def is_date_open(value: Any) -> bool:
    parsed = parse_date(value)
    if parsed is None:
        return True
    return parsed <= utc_now().date()


def normalize_slug(value: Any) -> str:
    text = clean_value(value).lower()
    text = re.sub(r"[^a-z0-9а-яё_-]+", "-", text, flags=re.IGNORECASE)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "novel"


def normalize_progress_percent(current: Any, total: Any) -> int:
    total_i = max(to_int(total), 0)
    if total_i <= 0:
        return 0
    current_i = min(max(to_int(current), 0), total_i)
    return round((current_i / total_i) * 100)
