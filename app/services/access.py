from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from ..utils import clean_value, is_date_open

ROLE_RANK = {"guest": 0, "traveler": 1, "keeper": 2}

@dataclass(frozen=True)
class AccessDecision:
    is_available: bool
    reason: str
    label: str
    required_role: str = "guest"


def normalize_required_role(value: Any) -> str:
    role = clean_value(value).lower()
    if role in {"keeper", "📜", "хранитель"}:
        return "keeper"
    if role in {"traveler", "subscriber", "🌱", "странствующий"}:
        return "traveler"
    if role in {"scheduled", "future"}:
        return "scheduled"
    if role in {"hidden", "not_translated", "no_content_source"}:
        return role
    return "guest"


def viewer_can_access_required_role(viewer: dict[str, Any] | None, required_role: str) -> bool:
    role = (viewer or {}).get("role") or "guest"
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(required_role, 0)


def decide_chapter_access(chapter: dict[str, Any], viewer: dict[str, Any] | None = None) -> AccessDecision:
    required = normalize_required_role(chapter.get("required_role"))
    if chapter.get("is_available") is True:
        return AccessDecision(True, "open", chapter.get("access_label") or "🌱 Открыто", required)
    if required == "scheduled":
        return AccessDecision(False, "free_scheduled", chapter.get("access_label") or "Откроется позже", required)
    if required in {"traveler", "keeper"} and viewer_can_access_required_role(viewer, required):
        return AccessDecision(True, "premium_open", chapter.get("access_label") or "Доступ открыт", required)
    if required == "keeper":
        return AccessDecision(False, "premium_denied", "📜 Ранний релиз Хранителя", required)
    if required == "traveler":
        return AccessDecision(False, "subscription_denied", "🌱 Доступ по подписке", required)
    return AccessDecision(False, "closed", chapter.get("access_label") or "Закрыто", required)
