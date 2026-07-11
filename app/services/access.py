"""Chapter and book access rules.

This service is the single place where the reader decides whether a viewer may
open a novel or a chapter. Page handlers and template-preparation helpers should
consume these decisions instead of reimplementing access checks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from ..utils import clean_value, is_date_open, parse_date, to_int, today_iso
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
    title: str = ""
    description: str = ""
    action_hint: str = ""
    primary_action: str = ""
    secondary_action: str = ""
    severity: str = "locked"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def format_release_date(value: Any) -> str:
    date_text = parse_date(value)
    if not date_text:
        return clean_value(value)
    try:
        value_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return date_text
    return value_date.strftime("%d.%m.%Y")


def role_display_name(role: Any) -> str:
    normalized = clean_value(role).lower()
    if normalized == "keeper":
        return "📜 Хранитель свитков"
    if normalized == "traveler":
        return "🌱 Странствующий читатель"
    return "читатель"


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
    """Backward-compatible generic copy for older templates."""
    if required_role == "keeper":
        return {
            "title": "Продолжение доступно Хранителю свитков",
            "description": "Хранитель свитков открывает ранние главы и помогает проектам выходить стабильнее.",
        }
    if required_role == "traveler":
        return {
            "title": "Новелла доступна подписчикам",
            "description": "🌱 Странствующий читатель открывает доступ к закрытым новеллам через приватную группу.",
        }
    return {
        "title": "Глава пока закрыта",
        "description": "Она откроется бесплатно по расписанию. Если доступ уже должен быть открыт, попробуйте проверить его ещё раз.",
    }


def enrich_access_decision(decision: AccessDecision, chapter: dict, novel: dict, profile: dict[str, Any]) -> AccessDecision:
    """Add reader-facing copy to a technical access decision."""
    status = decision.status
    release_label = format_release_date(decision.release_date)
    title = decision.title
    description = decision.description
    action_hint = decision.action_hint
    primary_action = decision.primary_action
    secondary_action = decision.secondary_action
    severity = decision.severity

    if status in {"public_open", "premium_open", "full_book_entitlement"}:
        title = title or "Глава открыта"
        description = description or "Можно читать полностью."
        primary_action = primary_action or "read"
        severity = "open"
    elif status == "book_access_denied":
        title = title or "Новелла доступна подписчикам 🌱"
        description = description or "Эта история лежит в закрытом доступе для Странствующих читателей. После вступления в приватную группу Mini App сам проверит доступ."
        action_hint = action_hint or "После оплаты Tribute добавит вас в приватную Telegram-группу. Затем вернитесь сюда и нажмите «Проверить доступ ещё раз»."
        primary_action = primary_action or "boosty"
        secondary_action = secondary_action or "refresh"
        severity = "subscription"
    elif status == "premium_scheduled":
        title = title or "Глава ещё не открылась"
        description = description or (f"Для вашего уровня доступа релиз запланирован на {release_label}." if release_label else "Для вашего уровня доступа релиз запланирован позже.")
        action_hint = action_hint or "Покупать ничего дополнительно не нужно — просто вернитесь после релиза."
        primary_action = primary_action or "back_to_toc"
        secondary_action = secondary_action or "refresh"
        severity = "scheduled"
    elif status == "free_scheduled":
        title = title or "Глава откроется бесплатно позже"
        description = description or (f"Бесплатный релиз запланирован на {release_label}. Ранний доступ можно открыть через 📜 Хранителя свитков, если для главы уже вышла премиум-версия." if release_label else "Бесплатный релиз запланирован позже. Ранний доступ можно открыть через 📜 Хранителя свитков, если для главы уже вышла премиум-версия.")
        action_hint = action_hint or "После оплаты Tribute добавит вас в приватную Telegram-группу. Затем вернитесь сюда и нажмите «Проверить доступ ещё раз»."
        primary_action = primary_action or "tribute"
        secondary_action = secondary_action or "refresh"
        severity = "scheduled"
    elif status == "not_translated":
        title = title or "Глава ещё не переведена"
        description = description or "Строка уже есть в оглавлении, но дата перевода ещё не проставлена. Как только глава будет готова и попадёт в расписание, статус изменится."
        primary_action = primary_action or "back_to_toc"
        severity = "draft"
    elif status == "no_content_source":
        title = title or "Глава готовится к публикации"
        description = description or "Перевод уже отмечен, но ссылка на текст ещё не добавлена. Это не проблема подписки — главе просто нужен источник для чтения."
        primary_action = primary_action or "back_to_toc"
        severity = "draft"
    elif status == "hidden":
        title = title or "Глава скрыта"
        description = description or "Эта строка временно скрыта из публичного оглавления. Обычным читателям она не открывается."
        primary_action = primary_action or "back_to_toc"
        severity = "hidden"
    else:
        title = title or "Доступ пока закрыт"
        description = description or "Mini App не смог открыть главу по текущим правилам доступа."
        primary_action = primary_action or "back_to_toc"
        secondary_action = secondary_action or "refresh"
        severity = "locked"

    return AccessDecision(
        allowed=decision.allowed,
        status=decision.status,
        url=decision.url,
        label=decision.label,
        class_name=decision.class_name,
        reason=decision.reason,
        required_role=decision.required_role,
        viewer_role=decision.viewer_role,
        release_date=decision.release_date,
        title=title,
        description=description,
        action_hint=action_hint,
        primary_action=primary_action,
        secondary_action=secondary_action,
        severity=severity,
    )


def access_paywall_copy(decision: AccessDecision, novel: dict, profile: dict[str, Any]) -> dict[str, Any]:
    """Return template-ready paywall copy and button visibility."""
    release_label = format_release_date(decision.release_date)
    can_show_boosty = decision.status in {"book_access_denied", "free_scheduled"}
    can_show_tribute = decision.status in {"book_access_denied", "free_scheduled"}
    can_refresh = decision.status in {"book_access_denied", "free_scheduled", "premium_scheduled", "locked"}
    required_label = role_display_name(decision.required_role)
    if decision.status in {"free_scheduled", "premium_scheduled"}:
        required_label = "дождаться даты релиза"
    elif decision.status in {"not_translated", "no_content_source"}:
        required_label = "готовый текст главы"
    return {
        "title": decision.title,
        "description": decision.description,
        "action_hint": decision.action_hint,
        "status": decision.status,
        "severity": decision.severity,
        "release_date": decision.release_date,
        "release_label": release_label,
        "required_role_label": required_label,
        "viewer_role_label": role_display_name(decision.viewer_role),
        "show_boosty": can_show_boosty,
        "show_tribute": can_show_tribute,
        "show_refresh": can_refresh,
        "show_back_to_toc": True,
    }


def chapter_toc_notice(decision: AccessDecision) -> dict[str, str]:
    """Short copy for locked rows in the table of contents."""
    release_label = format_release_date(decision.release_date)
    status = decision.status
    if status in {"public_open", "premium_open", "full_book_entitlement"}:
        return {"label": "", "hint": "", "class_name": "chapter-access-public"}
    if status == "free_scheduled":
        return {
            "label": f"Откроется {release_label}" if release_label else "Откроется позже",
            "hint": "Ранний доступ — через 📜",
            "class_name": "chapter-access-locked",
        }
    if status == "premium_scheduled":
        return {
            "label": f"📜 {release_label}" if release_label else "📜 по расписанию",
            "hint": "Уже в подписке, но ещё не настала дата релиза",
            "class_name": "chapter-access-keeper",
        }
    if status == "book_access_denied":
        return {"label": "Нужна 🌱 подписка", "hint": "Закрытая новелла", "class_name": "chapter-access-boosty"}
    if status == "not_translated":
        return {"label": "Ещё не переведена", "hint": "Глава в плане", "class_name": "chapter-access-hidden"}
    if status == "no_content_source":
        return {"label": "Готовится ссылка", "hint": "Нужен источник текста", "class_name": "chapter-access-hidden"}
    if status == "hidden":
        return {"label": "Скрыта", "hint": "Служебная строка", "class_name": "chapter-access-hidden"}
    return {"label": decision.label or "Закрыта", "hint": "", "class_name": decision.class_name}


def can_view_novel_for_profile(novel: dict, profile: dict[str, Any]) -> bool:
    """Return whether the novel card/TOC may be shown.

    🎁 novels are visible to guests too, but their chapters fail closed in
    decide_chapter_access() until the viewer has any subscription role
    (traveler or keeper) or a full-book entitlement. This lets the library show
    them in the subscription section instead of hiding them completely.
    """
    return True


def effective_role_for_novel(viewer: dict[str, Any], novel: dict) -> tuple[str, dict[str, Any]]:
    novel_id = to_int(novel.get("novel_id") or novel.get("id"), 0) or None
    profile = viewer_access_profile(viewer, novel_id)
    return clean_value(profile.get("role")) or "guest", profile


def _scheduled_date_for_role(chapter: dict, role: str) -> str:
    if role == "keeper":
        return clean_value(parse_date(chapter.get("premium_release_date")) or chapter.get("premium_release_date"))
    return clean_value(parse_date(chapter.get("free_release_date")) or chapter.get("free_release_date"))


def _decide_chapter_access_raw(chapter: dict, novel: dict, profile: dict[str, Any]) -> AccessDecision:
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
            label="Нужна 🌱 подписка",
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


def decide_chapter_access(chapter: dict, novel: dict, profile: dict[str, Any]) -> AccessDecision:
    return enrich_access_decision(_decide_chapter_access_raw(chapter, novel, profile), chapter, novel, profile)

def chapter_content_url_for_access(chapter: dict, novel: dict, profile: dict[str, Any]) -> str:
    """Return the only URL the current user may receive."""
    return decide_chapter_access(chapter, novel, profile).url
