"""Chapter and book access rules.

This service is the single place where the reader decides whether a viewer may
open a novel or a chapter. Page handlers and template-preparation helpers should
consume these decisions instead of reimplementing access checks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any

from .auth import role_rank, viewer_access_profile


@dataclass(frozen=True)
class AccessDecision:
    """Result of a chapter-level access check.

    ``allowed`` tells the route whether it may fetch and render the full chapter
    body. ``status`` is deliberately more precise than a boolean, so the UI can
    show the difference between a scheduled chapter, an untranslated row and a
    true access denial.
    """

    allowed: bool
    status: str
    url: str = ""
    label: str = ""
    class_name: str = "chapter-access-locked"
    reason: str = ""
    required_role: str = "guest"
    viewer_role: str = "guest"
    release_date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clean_value(value: Any) -> str:
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
    except ValueError:
        return default


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def parse_date(value: Any) -> str | None:
    text = clean_value(value)
    if not text:
        return None
    while len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
        text = text[1:-1].strip()
    if not text or text.lower() in {"null", "none", "undefined", "nan", "nat", "n/a", "na", "-", "—", '""', "''"}:
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
            pass
    return None


def is_date_open(value: Any) -> bool:
    date_text = parse_date(value)
    if not date_text:
        return False
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text):
        return True
    return date_text <= today_iso()


def novel_required_role(novel: dict) -> str:
    text = f"{novel.get('access_model', '')} {novel.get('early_access_mode', '')}".lower()
    if any(marker in text for marker in ("keeper", "хранитель", "📜")):
        return "keeper"
    if any(marker in text for marker in ("boostyonly", "boosty only", "boosty", "🎁")):
        return "traveler"
    return "guest"


def normalize_required_role(access_level: Any) -> str:
    text = clean_value(access_level).lower()
    if text in {"", "public", "free", "open", "guest"}:
        return "guest"
    if text in {"subscriber", "subscription", "boosty", "traveler", "reader", "stranger"}:
        return "traveler"
    if text in {"premium", "paid", "early", "keeper", "guardian", "all", "hidden"}:
        return "keeper"
    if any(marker in text for marker in ("boosty", "подпис", "странств")):
        return "traveler"
    return "keeper"


def viewer_can_access_required_role(viewer_role: str, required_role: str) -> bool:
    return role_rank(viewer_role) >= role_rank(required_role)


def novel_is_gift(novel: dict) -> bool:
    """A gift novel is visible only to Traveler, Keeper or a book owner.

    The source of truth is the 🎁 marker in Legend.PostIcons. AccessModel is
    accepted only as a backward-compatible fallback.
    """
    icons = clean_value(novel.get("post_icons"))
    model = clean_value(novel.get("access_model")).lower()
    return "🎁" in icons or "boostyonly" in model or "boosty only" in model


def novel_is_traveler_only(novel: dict) -> bool:
    # Backward-compatible alias used by older templates/helpers.
    return novel_is_gift(novel)


def chapter_is_translated(chapter: dict) -> bool:
    return bool(clean_value(chapter.get("translation_date")))


def chapter_public_url(chapter: dict) -> str:
    required = normalize_required_role(chapter.get("access_level"))
    free_url = clean_value(chapter.get("telegraph_free_url"))
    if free_url:
        return free_url
    if required == "guest":
        return clean_value(chapter.get("telegraph_url"))
    return ""


def chapter_premium_url(chapter: dict) -> str:
    """Return only the dedicated premium chapter source.

    A free/public URL must never be used as a premium fallback: otherwise a
    PremiumReleaseDate could accidentally expose the public copy before its
    FreeReleaseDate. Full-book access may still fall back to the free source in
    decide_chapter_access(), where that behaviour is explicit.
    """
    return clean_value(chapter.get("telegraph_premium_url"))


def chapter_public_ready(chapter: dict) -> bool:
    """Fail-closed check for an ordinary free release."""
    if not chapter_is_translated(chapter):
        return False
    release = clean_value(chapter.get("free_release_date"))
    if not release or not is_date_open(release):
        return False
    return bool(chapter_public_url(chapter))


def chapter_premium_ready(chapter: dict) -> bool:
    """Fail-closed check for a Keeper scheduled release."""
    if not chapter_is_translated(chapter):
        return False
    release = clean_value(chapter.get("premium_release_date"))
    if not release or not is_date_open(release):
        return False
    return bool(chapter_premium_url(chapter))


def chapter_content_url_for_role(chapter: dict, viewer_role: str) -> str:
    """Legacy helper kept for older code paths."""
    if chapter.get("is_visible") is not True:
        return ""
    if viewer_role == "keeper" and chapter_premium_ready(chapter):
        return chapter_premium_url(chapter)
    if chapter_public_ready(chapter):
        return chapter_public_url(chapter)
    return ""


def chapter_preview_url(chapter: dict) -> str:
    """Return a source only for a translated, scheduled locked chapter.

    The route that uses this helper must still return only the short server-side
    preview, never the source URL or the full chapter body.
    """
    if chapter.get("is_visible") is not True:
        return ""
    if not chapter_is_translated(chapter):
        return ""
    premium_release = clean_value(chapter.get("premium_release_date"))
    free_release = clean_value(chapter.get("free_release_date"))
    if not premium_release and not free_release:
        return ""
    return chapter_premium_url(chapter) or chapter_public_url(chapter)


def access_copy(required_role: str) -> dict[str, str]:
    if required_role == "keeper":
        return {
            "title": "Продолжение доступно Хранителю свитков",
            "description": "Хранитель свитков открывает все главы и все новеллы читалки",
        }
    return {
        "title": "Глава пока закрыта",
        "description": "Она откроется бесплатно по расписанию. Ранний релиз доступен 📜 Хранителю свитков; полный доступ к этой новелле также может быть выдан отдельной покупкой",
    }


def can_view_novel_for_profile(novel: dict, profile: dict[str, Any]) -> bool:
    if profile.get("has_full_book_access"):
        return True
    if not novel_is_gift(novel):
        return True
    return clean_value(profile.get("role")) in {"traveler", "keeper"}


def effective_role_for_novel(viewer: dict[str, Any], novel: dict) -> tuple[str, dict[str, Any]]:
    novel_id = to_int(novel.get("novel_id") or novel.get("id"), 0) or None
    profile = viewer_access_profile(viewer, novel_id)
    return clean_value(profile.get("role")) or "guest", profile


def _scheduled_date_for_role(chapter: dict, role: str) -> str:
    if role == "keeper":
        return clean_value(parse_date(chapter.get("premium_release_date")) or chapter.get("premium_release_date"))
    return clean_value(parse_date(chapter.get("free_release_date")) or chapter.get("free_release_date"))


def decide_chapter_access(chapter: dict, novel: dict, profile: dict[str, Any]) -> AccessDecision:
    """Return a precise access decision for a chapter.

    Rules:
    - Traveler only gains visibility of 🎁 novels; premium dates do not open chapters.
    - Keeper reads chapters after PremiumReleaseDate.
    - A full-book entitlement reads every translated chapter of that novel.
    - Everyone may read chapters after FreeReleaseDate.
    - Hidden chapter rows fail closed for ordinary users.
    """
    role = clean_value(profile.get("role")) or "guest"
    required_role = normalize_required_role(chapter.get("access_level"))

    if chapter.get("is_visible") is not True and role != "keeper" and not profile.get("has_full_book_access"):
        return AccessDecision(
            allowed=False,
            status="hidden",
            label="Глава скрыта",
            class_name="chapter-access-hidden",
            reason="chapter_is_hidden",
            required_role=required_role,
            viewer_role=role,
        )

    if not chapter_is_translated(chapter):
        return AccessDecision(
            allowed=False,
            status="not_translated",
            label="Ещё не переведена",
            class_name="chapter-access-hidden",
            reason="missing_translation_date",
            required_role=required_role,
            viewer_role=role,
        )

    if profile.get("has_full_book_access"):
        url = chapter_premium_url(chapter) or chapter_public_url(chapter)
        if url:
            return AccessDecision(
                allowed=True,
                status="full_book_entitlement",
                url=url,
                label="Открыта",
                class_name="chapter-access-public",
                reason="full_book_entitlement",
                required_role=required_role,
                viewer_role=role,
            )

    if novel_is_gift(novel) and role == "guest":
        return AccessDecision(
            allowed=False,
            status="book_access_denied",
            label="Доступно подписчикам",
            class_name="chapter-access-locked",
            reason="gift_novel_requires_subscription",
            required_role="traveler",
            viewer_role=role,
        )

    if role == "keeper" and chapter_premium_ready(chapter):
        return AccessDecision(
            allowed=True,
            status="premium_open",
            url=chapter_premium_url(chapter),
            label="Открыта",
            class_name="chapter-access-public",
            reason="premium_release_open",
            required_role=required_role,
            viewer_role=role,
        )

    if chapter_public_ready(chapter):
        return AccessDecision(
            allowed=True,
            status="public_open",
            url=chapter_public_url(chapter),
            label="Открыта",
            class_name="chapter-access-public",
            reason="free_release_open",
            required_role=required_role,
            viewer_role=role,
        )

    if role == "keeper":
        return AccessDecision(
            allowed=False,
            status="premium_scheduled",
            label="Откроется по расписанию",
            class_name="chapter-access-keeper",
            reason="premium_release_not_open",
            required_role=required_role,
            viewer_role=role,
            release_date=_scheduled_date_for_role(chapter, role),
        )

    if not chapter_public_url(chapter) and not chapter_premium_url(chapter):
        return AccessDecision(
            allowed=False,
            status="no_content_source",
            label="Глава пока недоступна",
            class_name="chapter-access-hidden",
            reason="missing_telegraph_source",
            required_role=required_role,
            viewer_role=role,
        )

    return AccessDecision(
        allowed=False,
        status="free_scheduled",
        label="Откроется бесплатно позже",
        class_name="chapter-access-locked",
        reason="free_release_not_open",
        required_role=required_role,
        viewer_role=role,
        release_date=_scheduled_date_for_role(chapter, role),
    )


def chapter_content_url_for_access(chapter: dict, novel: dict, profile: dict[str, Any]) -> str:
    """Return the only URL the current user may receive."""
    return decide_chapter_access(chapter, novel, profile).url
