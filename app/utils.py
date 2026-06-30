from __future__ import annotations

from datetime import date, datetime
from typing import Any
import re


def clean(value: Any, default: str = '') -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == '':
            return default
        return int(float(str(value).replace(',', '.')))
    except (TypeError, ValueError):
        return default


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'да', 'истина'}


def slugify(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r'[^a-z0-9а-яё_-]+', '-', text, flags=re.I).strip('-')
    return text or 'novel'


def parse_tags(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    parts = re.split(r'[,;\n|]+', text)
    return [p.strip() for p in parts if p.strip()]


def parse_date(value: Any) -> date | None:
    text = clean(value)
    if not text:
        return None
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d.%m.%y'):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def is_open_date(value: Any) -> bool:
    parsed = parse_date(value)
    return parsed is None or parsed <= date.today()
