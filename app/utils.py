"""Small shared normalization helpers used by services.

The project receives data from Google Sheets, Supabase/PostgREST, Telegram and
client-side localStorage. These sources often represent "empty" and numeric
values differently, so primitive parsing must be centralized. Keeping these
helpers in one module prevents subtle drift between sync, catalog, access and
user-state code.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

EMPTY_TEXT_VALUES = {
    "nan", "none", "null", "undefined", "nat", "n/a", "na", "-", "—", '""', "''",
}
TRUE_TEXT_VALUES = {"true", "1", "yes", "y", "да", "истина", "visible", "show", "✓", "✅"}
FALSE_TEXT_VALUES = {"false", "0", "no", "n", "нет", "ложь", "hidden", "hide", "✕", "❌"}


def clean_value(value: Any) -> str:
    """Return a safe stripped string, treating common pseudo-empty values as empty."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "undefined"}:
        return ""
    return text


def to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    text = clean_value(value).replace("%", "").replace(",", ".")
    if not text:
        return default
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = clean_value(value).replace("%", "").replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = clean_value(value).lower()
    if not text:
        return default
    if text in TRUE_TEXT_VALUES:
        return True
    if text in FALSE_TEXT_VALUES:
        return False
    return default


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def today_iso() -> str:
    return utc_now().date().isoformat()


def parse_date(value: Any) -> str | None:
    """Normalize a spreadsheet/Supabase date into YYYY-MM-DD or None.

    Supabase DATE columns must receive either ISO date strings or JSON null.
    Google Sheets formulas can leak visually-empty strings and repeatedly quoted
    values; those are normalized to None before they can reach access checks or
    database writes.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    text = str(value).strip()
    if not text:
        return None

    text = text.replace('\\"', '"').replace("\\'", "'").strip()
    for _ in range(5):
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
            text = text[1:-1].strip()
        else:
            break

    if not text or text.lower() in EMPTY_TEXT_VALUES:
        return None

    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[T\s].*)?$", text)
    if iso_match:
        candidate = iso_match.group(1)
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None

    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y.%m.%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def is_date_open(value: Any) -> bool:
    date_text = parse_date(value)
    if not date_text:
        return False
    return date_text <= today_iso()



def normalize_progress_percent(value: Any) -> float | int:
    """Normalize a progress percentage from Sheets/Supabase into 0..100.

    Some sources store percent as 43, 43.0, "43%" or accidentally as 4300.
    Values above 100 are repeatedly divided by 100, then clamped.
    """
    progress = to_float(value, 0.0)
    while progress > 100:
        progress = progress / 100
    progress = max(0.0, min(100.0, progress))
    return int(progress) if float(progress).is_integer() else round(progress, 1)

def normalize_slug(value: Any) -> str:
    text = clean_value(value).lower().replace("ё", "е")
    text = re.sub(r"[^\wа-яА-Я-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "item"
