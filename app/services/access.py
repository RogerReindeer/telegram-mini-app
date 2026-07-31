"""Chapter and book access rules.

This service is the single place where the reader decides whether a viewer may
open a novel or a chapter. Page handlers and template-preparation helpers should
consume these decisions instead of reimplementing access checks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Any

from ..utils import clean_value, is_date_open, parse_chapter_id, parse_date, to_bool, to_int, today_iso
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
    if text in {"", "public", "free", "open", "guest", "none", "anonymous", "unsubscribed", "no_subscription", "без подписки"}:
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
    """Return whether the novel is subscription-only.

    The only source of truth is the 🎁 marker from Legend.PostIcons. Legacy
    AccessModel values must not move an ordinary novel to the subscriber-only
    section.
    """
    return "🎁" in clean_value(novel.get("post_icons"))


def novel_is_traveler_only(novel: dict) -> bool:
    # Backward-compatible alias used by older templates/helpers.
    return novel_is_gift(novel)


_TELEGRAPH_URL_RE = re.compile(r"^https?://(?:www\.)?telegra\.ph/[^\s?#]+", re.IGNORECASE)
_TELETYPE_URL_RE = re.compile(
    r"^https?://(?:www\.)?teletype\.in/(?!files/)[^\s?#]+", re.IGNORECASE
)
_TELEGRAPH_PATH_RE = re.compile(r"^[^\s/]+-\d{2}-\d{2}(?:-\d+)?$", re.IGNORECASE)


def normalize_readable_chapter_source(value: Any) -> str:
    """Return a real chapter page supported by the reader.

    Accepted sources are full Telegraph pages, complete Telegraph paths and
    full Teletype article URLs. Short CRM codes such as ``96ZS0EQO`` remain
    metadata and never make a chapter readable on their own.
    """
    text = clean_value(value)
    if not text:
        return ""
    if text.startswith("http://"):
        text = "https://" + text[len("http://"):]
    if (
        _TELEGRAPH_URL_RE.match(text)
        or _TELETYPE_URL_RE.match(text)
        or _TELEGRAPH_PATH_RE.match(text)
    ):
        return text
    return ""


def normalize_readable_telegraph_source(value: Any) -> str:
    """Backward-compatible alias for the generic chapter source validator."""
    return normalize_readable_chapter_source(value)


def chapter_is_translated(chapter: dict) -> bool:
    # A real readable source is stronger evidence than a missing legacy
    # TranslationDate. Bare internal codes do not count as translated content.
    return bool(
        clean_value(chapter.get("translation_date"))
        or chapter_content_source(chapter, "telegraph_free_url", "telegraph_free_code")
        or chapter_content_source(chapter, "telegraph_premium_url", "telegraph_premium_code")
    )


def chapter_content_source(chapter: dict, url_key: str, code_key: str) -> str:
    """Return a genuinely readable Telegraph URL/path, failing closed.

    ``Telegraph*Code`` in Translation CRM is only a technical identifier. It
    must never make a chapter readable or increase library counters without a
    real value in ``Telegraph*URL``. ``code_key`` stays in the signature only
    for compatibility with older callers.
    """
    del code_key
    return normalize_readable_chapter_source(chapter.get(url_key))


def chapter_public_url(chapter: dict) -> str:
    required = normalize_required_role(chapter.get("access_level"))
    free_url = chapter_content_source(chapter, "telegraph_free_url", "telegraph_free_code")
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
    return chapter_content_source(chapter, "telegraph_premium_url", "telegraph_premium_code")


def chapter_has_real_source(chapter: dict) -> bool:
    return bool(chapter_public_url(chapter) or chapter_premium_url(chapter))


_NOVEL_STATUS_BOUNDARY_RE = re.compile(r"^(\d+)(?:[-./](\d+))?$")


def parse_novel_status_boundary(value: Any) -> tuple[int, int | None] | None:
    """Parse a NovelStatus boundary such as ``20`` or ``12-1``."""
    text = clean_value(value)
    if not text:
        return None
    normalized = re.sub(r"(?:часть|part)", "-", text, flags=re.IGNORECASE)
    normalized = re.sub(r"[–—−]", "-", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    match = _NOVEL_STATUS_BOUNDARY_RE.fullmatch(normalized)
    if not match:
        return None
    return int(match.group(1)), (int(match.group(2)) if match.group(2) else None)


def chapter_semantic_position(chapter: dict) -> tuple[int, int]:
    """Return SourceChapterNo/PartNo without assuming a ChapterID formula."""
    parsed = parse_chapter_id(chapter.get("chapter_id") or chapter.get("chapter_code")) or {}
    source_text = clean_value(chapter.get("source_chapter_no"))
    source_no = to_int(source_text, -1) if source_text else to_int(parsed.get("chapter_no"), -1)
    if source_no < 0:
        source_no = max(0, to_int(chapter.get("chapter_no"), 0))
    part_text = clean_value(chapter.get("part_no"))
    part_no = to_int(part_text, 0) if part_text else to_int(parsed.get("part_no"), 0)
    return source_no, max(0, part_no)


def chapter_technical_order(chapter: dict) -> tuple[int, int, int, str]:
    """Return stable reading order; ChapterNo is the technical sequence."""
    source_no, part_no = chapter_semantic_position(chapter)
    chapter_no = to_int(chapter.get("chapter_no"), 0)
    if chapter_no <= 0:
        chapter_no = 1_000_000 + max(0, source_no) * 100 + max(0, part_no)
    return (
        chapter_no,
        max(0, source_no),
        max(0, part_no),
        clean_value(chapter.get("chapter_id") or chapter.get("id")),
    )


def novel_status_boundary_count_hint(value: Any) -> int:
    """Return the minimum technical-row count encoded by a boundary.

    ``12-1`` is the thirteenth reading unit when the old CRM row lost its
    SourceChapterNo/PartNo split.  The value is only a query/recovery hint; the
    full list resolver below still prefers a real semantic endpoint.
    """
    boundary = parse_novel_status_boundary(value)
    if not boundary:
        return 0
    chapter_no, part_no = boundary
    return max(0, chapter_no + (part_no or 0))


def chapter_matches_novel_status_endpoint(chapter: dict, value: Any) -> bool:
    boundary = parse_novel_status_boundary(value)
    if not boundary:
        return False
    source_no, part_no = chapter_semantic_position(chapter)
    boundary_no, boundary_part = boundary
    if source_no != boundary_no:
        return False
    if boundary_part is None:
        # A bare chapter number means the first reading unit of that source
        # chapter.  Later split parts require an explicit ``N-P`` endpoint.
        return part_no in {0, 1}
    return part_no == boundary_part


def chapter_within_novel_status_boundary(chapter: dict, value: Any) -> bool:
    """Compatibility check for callers that only have one chapter row.

    Exact access is resolved by ``resolve_novel_status_access_ids`` because a
    boundary is an endpoint in the technical chapter order, not a numeric
    count.  This helper deliberately excludes later split parts for a bare
    boundary such as ``1``.
    """
    boundary = parse_novel_status_boundary(value)
    if not boundary:
        return False
    source_no, part_no = chapter_semantic_position(chapter)
    boundary_no, boundary_part = boundary
    if source_no < boundary_no:
        return True
    if source_no > boundary_no:
        return False
    if boundary_part is None:
        return part_no in {0, 1}
    return part_no <= boundary_part


def resolve_novel_status_access_ids(
    chapters: list[dict], value: Any, declared_count: Any = None
) -> set[str]:
    """Resolve a NovelStatus endpoint or stored count to readable chapter rows.

    Production may temporarily contain a mixed snapshot: chapter URLs are
    current, while the endpoint columns or per-row access flags are stale.  The
    stored novel counters are therefore a supported recovery source, not merely
    a UI number. Rows without a real Telegraph/Teletype source never open.
    """
    boundary = parse_novel_status_boundary(value)
    declared = max(0, to_int(declared_count, 0))

    ordered = sorted((dict(chapter) for chapter in chapters or []), key=chapter_technical_order)
    source_backed = [chapter for chapter in ordered if chapter_has_real_source(chapter)]
    if declared > 0:
        return {
            clean_value(chapter.get("chapter_id") or chapter.get("id"))
            for chapter in source_backed[:declared]
            if clean_value(chapter.get("chapter_id") or chapter.get("id"))
        }
    if not boundary:
        return set()

    endpoint_index: int | None = None
    boundary_no, boundary_part = boundary
    for index, chapter in enumerate(ordered):
        source_no, part_no = chapter_semantic_position(chapter)
        if source_no != boundary_no:
            continue
        if boundary_part is None:
            endpoint_index = index
            break
        if part_no == boundary_part:
            endpoint_index = index
            break

    if endpoint_index is None:
        ordinal = novel_status_boundary_count_hint(value)
        if ordinal <= 0 or not ordered:
            return set()
        endpoint_index = min(len(ordered), ordinal) - 1

    return {
        clean_value(chapter.get("chapter_id") or chapter.get("id"))
        for chapter in ordered[: endpoint_index + 1]
        if chapter_has_real_source(chapter)
        and clean_value(chapter.get("chapter_id") or chapter.get("id"))
    }


def _novel_access_count(novel: dict, *keys: str) -> int:
    return max((max(0, to_int(novel.get(key), 0)) for key in keys), default=0)


def apply_novel_status_access_boundaries(chapters: list[dict], novel: dict) -> list[dict]:
    """Rebuild effective 🌱/📜 access from endpoints, counters and real URLs.

    Endpoint columns remain preferred. Stored counters recover access when a
    partial sync or an older Supabase schema lost those endpoint values. For an
    ordinary novel, an already released free URL is also public even if stale
    boolean flags say otherwise. Gift novels never receive that public fallback.
    """
    chapter_rows = [dict(chapter) for chapter in chapters or []]
    traveler_boundary = clean_value(novel.get("traveler_access_through"))
    keeper_boundary = clean_value(novel.get("keeper_access_through")) or traveler_boundary
    is_gift = novel_is_gift(novel)

    traveler_count = _novel_access_count(
        novel,
        "traveler_chapters_count",
        "subscriber_chapters",
        "free_chapters_count",
        "free_chapters",
    )
    keeper_count = max(
        traveler_count,
        _novel_access_count(novel, "keeper_chapters_count", "keeper_chapters"),
    )

    traveler_ids = resolve_novel_status_access_ids(
        chapter_rows, traveler_boundary, traveler_count
    )
    keeper_ids = resolve_novel_status_access_ids(
        chapter_rows, keeper_boundary, keeper_count
    )

    # Preserve positive flags from a successful schema-19 sync. False flags are
    # not authoritative because they are exactly what stale snapshots produced.
    for chapter in chapter_rows:
        chapter_id = clean_value(chapter.get("chapter_id") or chapter.get("id"))
        if not chapter_id or not chapter_has_real_source(chapter):
            continue
        if to_bool(chapter.get("traveler_access"), False):
            traveler_ids.add(chapter_id)
        if to_bool(chapter.get("keeper_access"), False):
            keeper_ids.add(chapter_id)

        if not is_gift:
            free_url = chapter_public_url(chapter)
            free_date = clean_value(chapter.get("free_release_date"))
            if free_url and free_date and is_date_open(free_date):
                traveler_ids.add(chapter_id)

    keeper_ids.update(traveler_ids)

    result: list[dict] = []
    keeper_order = 0
    for chapter in sorted(chapter_rows, key=chapter_technical_order):
        prepared = dict(chapter)
        chapter_id = clean_value(prepared.get("chapter_id") or prepared.get("id"))
        traveler_allowed = bool(chapter_id and chapter_id in traveler_ids)
        keeper_allowed = bool(chapter_id and chapter_id in keeper_ids)
        if keeper_allowed and not traveler_allowed:
            keeper_order += 1

        prepared["traveler_access"] = traveler_allowed
        prepared["traveler_access_source"] = (
            "effective_snapshot" if traveler_allowed else None
        )
        prepared["keeper_access"] = keeper_allowed
        prepared["keeper_access_order"] = (
            keeper_order if keeper_allowed and not traveler_allowed else None
        )
        prepared["keeper_access_source"] = (
            "effective_snapshot" if keeper_allowed else None
        )
        result.append(prepared)
    return result


def _has_explicit_novel_status_marker(chapter: dict, role: str) -> bool:
    source_key = "keeper_access_source" if role == "keeper" else "traveler_access_source"
    return clean_value(chapter.get(source_key)).lower() == "novel_status"


def _access_field_present(chapter: dict, role: str) -> bool:
    marker_key = "_keeper_access_field_present" if role == "keeper" else "_traveler_access_field_present"
    field_key = "keeper_access" if role == "keeper" else "traveler_access"
    if marker_key in chapter:
        return bool(chapter.get(marker_key))
    return field_key in chapter


def chapter_traveler_access_enabled(chapter: dict, novel: dict | None = None) -> bool:
    """Resolve the 🌱 boundary with safe recovery for an incomplete deployment.

    Preferred order:
    1. explicit per-chapter flag produced by MiniAppSync schema 19;
    2. the novel-level ``traveler_access_through`` value from NovelStatus;
    3. legacy released public URL only when NovelStatus data is not present yet.

    The fallback prevents a schema/cache mismatch from closing the whole reader,
    while the next successful schema-19 sync restores the strict source of truth.
    """
    if _has_explicit_novel_status_marker(chapter, "traveler"):
        return to_bool(chapter.get("traveler_access"), False)
    if to_bool(chapter.get("traveler_access"), False):
        return True

    boundary = clean_value((novel or {}).get("traveler_access_through"))
    if boundary:
        return chapter_within_novel_status_boundary(chapter, boundary)
    if _access_field_present(chapter, "traveler"):
        return False

    release = clean_value(chapter.get("free_release_date"))
    return bool(release and is_date_open(release) and chapter_public_url(chapter))


def chapter_traveler_url(chapter: dict, novel: dict | None = None) -> str:
    """Return the source opened by the 🌱 NovelStatus boundary."""
    if not chapter_traveler_access_enabled(chapter, novel):
        return ""
    return chapter_public_url(chapter) or chapter_premium_url(chapter)


def chapter_guest_free_url(chapter: dict, novel: dict | None = None) -> str:
    """Return a genuinely free source for a viewer without subscriptions.

    NovelStatus 🌱 remains the primary boundary.  The released free-link
    fallback protects public chapters when an older or partially applied sync
    left an explicit ``traveler_access=false`` flag in Supabase.  Gift novels
    never use this fallback: their 🌱 range still requires the Traveler role.
    """
    if novel_is_gift(novel or {}):
        return ""

    traveler_url = chapter_traveler_url(chapter, novel)
    if traveler_url:
        return traveler_url

    public_url = chapter_public_url(chapter)
    free_release_date = clean_value(chapter.get("free_release_date"))
    if public_url and free_release_date and is_date_open(free_release_date):
        return public_url
    return ""


def chapter_public_ready(chapter: dict, novel: dict | None = None) -> bool:
    return bool(chapter_traveler_url(chapter, novel))


def chapter_keeper_access_enabled(chapter: dict, novel: dict | None = None) -> bool:
    """Resolve the 📜 boundary, with Keeper inheriting the full 🌱 range."""
    if chapter_traveler_access_enabled(chapter, novel):
        return True
    if _has_explicit_novel_status_marker(chapter, "keeper"):
        return to_bool(chapter.get("keeper_access"), False)
    if to_bool(chapter.get("keeper_access"), False):
        return True

    boundary = clean_value((novel or {}).get("keeper_access_through")) or clean_value(
        (novel or {}).get("traveler_access_through")
    )
    if boundary:
        return chapter_within_novel_status_boundary(chapter, boundary)
    if _access_field_present(chapter, "keeper"):
        return False

    release = clean_value(chapter.get("premium_release_date"))
    legacy_released = bool(release and is_date_open(release) and chapter_premium_url(chapter))
    return legacy_released


def chapter_keeper_url(chapter: dict, novel: dict | None = None) -> str:
    if not chapter_keeper_access_enabled(chapter, novel):
        return ""
    if chapter_traveler_access_enabled(chapter, novel):
        return chapter_public_url(chapter) or chapter_premium_url(chapter)
    return chapter_premium_url(chapter) or chapter_public_url(chapter)


def chapter_premium_ready(chapter: dict, novel: dict | None = None) -> bool:
    return bool(chapter_keeper_url(chapter, novel))


def chapter_subscription_url(
    chapter: dict, viewer_role: str = "traveler", novel: dict | None = None
) -> str:
    if clean_value(viewer_role).lower() == "keeper":
        return chapter_keeper_url(chapter, novel)
    return chapter_traveler_url(chapter, novel)


def chapter_subscription_ready(
    chapter: dict, viewer_role: str = "traveler", novel: dict | None = None
) -> bool:
    return bool(chapter_subscription_url(chapter, viewer_role, novel))


def chapter_content_url_for_role(
    chapter: dict, viewer_role: str, novel: dict | None = None
) -> str:
    """Legacy helper kept for older code paths."""
    if chapter.get("is_visible") is not True:
        return ""
    if clean_value(viewer_role).lower() == "keeper":
        return chapter_keeper_url(chapter, novel)
    return chapter_traveler_url(chapter, novel)

def chapter_preview_url(chapter: dict) -> str:
    """Locked chapter previews are disabled.

    A closed chapter must never expose its source URL or any fragment of its
    text. The helper remains only for backward compatibility and always
    returns an empty value.
    """
    return ""


def access_copy(required_role: str) -> dict[str, str]:
    """Backward-compatible generic copy for older templates."""
    if required_role == "keeper":
        return {
            "title": "Упс… эта глава по платной подписке",
            "description": (
                "Для чтения оформите 📜 «Хранителя свитков». Этот уровень открывает "
                "ближайшие ранние главы в пределах границы 📜, заданной для новеллы."
            ),
        }
    if required_role == "traveler":
        return {
            "title": "Эта новелла доступна по подписке",
            "description": (
                "Для чтения новеллы с 🎁 оформите 🌱 «Странствующего читателя». "
                "Этот уровень нужен только для новелл с подарком."
            ),
        }
    return {
        "title": "Глава пока закрыта",
        "description": "Она ещё не вошла в доступ. Если глава должна быть открыта, проверьте доступ ещё раз.",
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
    viewer_role = normalize_required_role(profile.get("role") or decision.viewer_role or "guest")

    if status in {"public_open", "premium_open", "subscription_open", "full_book_entitlement"}:
        title = title or "Глава открыта"
        description = description or "Можно читать полностью."
        primary_action = primary_action or "read"
        severity = "open"
    elif status == "book_access_denied":
        title = title or "Эта новелла доступна по подписке"
        description = description or (
            "Новелла отмечена 🎁. Для чтения оформите 🌱 «Странствующего читателя». "
            "В обычных новеллах этот уровень не расширяет бесплатный доступ."
        )
        action_hint = action_hint or (
            "После оформления вернитесь в Mini App и нажмите «Проверить доступ»."
        )
        primary_action = primary_action or "buy_traveler"
        secondary_action = secondary_action or "refresh"
        severity = "subscription"
    elif status == "premium_scheduled":
        title = title or "Упс… эта глава пока закрыта"
        if viewer_role == "keeper":
            description = description or (
                f"📜 «Хранитель свитков» активен, но эта глава откроется {release_label}."
                if release_label
                else "📜 «Хранитель свитков» активен, но эта глава пока не вошла в границу 📜 этой новеллы."
            )
            action_hint = action_hint or "Покупать другую подписку не нужно — дождитесь расширения доступа."
        else:
            description = description or (
                f"Глава пока не входит ни в бесплатный, ни в платный диапазон и откроется {release_label}."
                if release_label
                else "Глава пока не входит ни в бесплатный, ни в платный диапазон доступа."
            )
            action_hint = action_hint or "Подписка не откроет эту главу раньше, пока она не войдёт в доступ."
        primary_action = primary_action or "wait"
        secondary_action = secondary_action or "refresh"
        severity = "scheduled"
    elif status == "free_scheduled":
        keeper_available = bool(chapter_keeper_url(chapter, novel))
        if keeper_available:
            title = title or "Упс… эта глава по платной подписке"
            if novel_is_gift(novel):
                description = description or (
                    "Основные главы этой новеллы с 🎁 открывает 🌱 «Странствующий читатель», "
                    "но эта глава относится к раннему доступу 📜. Для чтения оформите "
                    "«Хранителя свитков»."
                )
            else:
                description = description or (
                    "Эта глава входит в ранний доступ 📜. Для чтения оформите "
                    "подписку «Хранитель свитков»."
                )
            action_hint = action_hint or (
                "Количество ранних глав задаётся отдельно для каждой новеллы — обычно это одна или две главы. "
                "После оформления вернитесь сюда и нажмите «Проверить доступ»."
            )
            primary_action = primary_action or "upgrade_keeper"
        else:
            title = title or "Глава пока закрыта"
            description = description or (
                f"Она откроется {release_label}."
                if release_label
                else "Глава ещё не вошла ни в бесплатный, ни в подписочный диапазон доступа."
            )
            action_hint = action_hint or "Покупать подписку ради этой главы пока не нужно."
            primary_action = primary_action or "wait"
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


def access_paywall_copy(
    decision: AccessDecision,
    novel: dict,
    profile: dict[str, Any],
    chapter: dict | None = None,
) -> dict[str, Any]:
    """Return role-aware paywall copy and only the purchase that unlocks this page.

    🌱 is sold only inside a 🎁 novel and only to unlock that novel. It never
    expands the free range of an ordinary novel. 📜 is offered for Keeper-only
    early chapters in any novel. The current chapter therefore never shows two
    competing subscription offers.
    """
    release_label = format_release_date(decision.release_date)
    viewer_role = clean_value(profile.get("role") or decision.viewer_role) or "guest"
    viewer_rank = role_rank(viewer_role)
    is_gift_novel = novel_is_gift(novel)

    buy_traveler = (
        decision.primary_action in {"buy_traveler", "choose_subscription"}
        and is_gift_novel
    )
    upgrade_keeper = decision.primary_action == "upgrade_keeper"
    can_refresh = decision.status in {
        "book_access_denied", "free_scheduled", "premium_scheduled", "locked"
    }

    show_traveler_purchase = buy_traveler and viewer_rank < role_rank("traveler")
    show_keeper_purchase = upgrade_keeper and viewer_rank < role_rank("keeper")
    traveler_already_owned = viewer_rank >= role_rank("traveler")
    keeper_already_owned = viewer_rank >= role_rank("keeper")
    show_subscription_choices = show_traveler_purchase or show_keeper_purchase

    if viewer_role == "keeper":
        owned_message = (
            "📜 «Хранитель свитков» активен. Вам доступны новеллы с 🎁 и ранние "
            "главы в пределах границы 📜 каждой новеллы."
        )
    elif viewer_role == "traveler":
        owned_message = (
            "🌱 «Странствующий читатель» активен. Вы можете читать новеллы с 🎁. "
            "Ранние закрытые главы открывает 📜 «Хранитель свитков»."
        )
    else:
        owned_message = ""

    if buy_traveler:
        unlock_button_label = "Оформить Странствующего читателя"
        panel_title = "Подписка для новеллы с 🎁"
        panel_description = (
            "🌱 «Странствующий читатель» открывает доступ к чтению этой новеллы с 🎁. "
            "В обычных новеллах он не добавляет платные главы."
        )
    elif upgrade_keeper:
        unlock_button_label = "Оформить Хранителя свитков"
        panel_title = "Ранний доступ к главам"
        panel_description = (
            "📜 «Хранитель свитков» открывает ближайшие закрытые главы в пределах "
            "уровня 📜, установленного для этой новеллы. Обычно это одна или две главы."
        )
    else:
        unlock_button_label = ""
        panel_title = "Доступ к главе"
        panel_description = "Проверьте текущий доступ или вернитесь к оглавлению."

    required_label = role_display_name(decision.required_role)
    if decision.primary_action == "wait":
        required_label = "дождаться открытия главы"
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
        "viewer_role_label": role_display_name(viewer_role),
        "viewer_role": viewer_role,
        "show_boosty": False,
        "show_tribute": show_subscription_choices,
        "show_traveler_purchase": show_traveler_purchase,
        "show_keeper_purchase": show_keeper_purchase,
        "traveler_already_owned": traveler_already_owned,
        "keeper_already_owned": keeper_already_owned,
        "already_owned_message": owned_message,
        "show_refresh": can_refresh,
        "show_back_to_toc": True,
        "show_subscription_help": decision.status in {
            "book_access_denied", "free_scheduled", "premium_scheduled"
        },
        "unlock_button_label": unlock_button_label,
        "panel_title": panel_title,
        "panel_description": panel_description,
        "traveler_option_title": "🌱 Странствующий читатель",
        "traveler_option_description": (
            "Только чтение новелл с 🎁. Бесплатный диапазон обычных новелл не меняется."
        ),
        "keeper_option_title": "📜 Хранитель свитков",
        "keeper_option_description": (
            "Ближайшие ранние главы по границе 📜 каждой новеллы; обычно одна или две."
        ),
    }


def chapter_toc_notice(decision: AccessDecision) -> dict[str, str]:
    """Short copy for locked rows in the table of contents."""
    release_label = format_release_date(decision.release_date)
    status = decision.status
    if status == "public_open":
        return {"label": "", "hint": "", "class_name": "chapter-access-public"}
    if status in {"premium_open", "subscription_open"}:
        return {
            "label": "🔓 По подписке",
            "hint": "Глава открыта благодаря подписке",
            "class_name": "chapter-access-subscription",
        }
    if status == "full_book_entitlement":
        return {"label": "Открыта покупкой", "hint": "Доступ к книге куплен отдельно", "class_name": "chapter-access-public"}
    if status == "free_scheduled":
        return {
            "label": f"Откроется {release_label}" if release_label else "Откроется позже",
            "hint": "Ранний доступ по 📜 «Хранителю свитков»",
            "class_name": "chapter-access-locked",
        }
    if status == "premium_scheduled":
        if decision.required_role == "traveler":
            return {
                "label": f"🔒 {release_label}" if release_label else "🔒 По подписке",
                "hint": "Разблокируется по подписке после даты релиза",
                "class_name": "chapter-access-keeper",
            }
        return {
            "label": f"📜 {release_label}" if release_label else "📜 по расписанию",
            "hint": "Уже в подписке, но ещё не настала дата релиза",
            "class_name": "chapter-access-keeper",
        }
    if status == "book_access_denied":
        return {
            "label": f"🔒 {release_label}" if release_label else "🔒 По подписке",
            "hint": "Новелла с 🎁: нужен 🌱 «Странствующий читатель»",
            "class_name": "chapter-access-boosty",
        }
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
    """Choose the date shown in the TOC; it does not grant access."""
    role = clean_value(role).lower()
    if role == "keeper":
        value = chapter.get("premium_release_date") or chapter.get("free_release_date")
    else:
        value = chapter.get("free_release_date") or chapter.get("premium_release_date")
    return clean_value(parse_date(value) or value)


def _decide_chapter_access_raw(chapter: dict, novel: dict, profile: dict[str, Any]) -> AccessDecision:
    """Decide access strictly from the NovelStatus role flags.

    ``FreeReleaseDate`` and ``PremiumReleaseDate`` are display metadata only.
    The 🌱 boundary opens ordinary novels to guests/Traveler and gift novels to
    Traveler. The 📜 boundary opens the Keeper range.
    """
    role = normalize_required_role(profile.get("role") or "guest")
    is_gift_novel = novel_is_gift(novel)
    required_role = "traveler" if is_gift_novel else "guest"

    if (
        chapter.get("is_visible") is not True
        and not is_gift_novel
        and role != "keeper"
        and not profile.get("has_full_book_access")
    ):
        return AccessDecision(
            allowed=False, status="hidden", label="Глава скрыта",
            class_name="chapter-access-hidden", reason="chapter_is_hidden",
            required_role=required_role, viewer_role=role,
        )

    if not chapter_is_translated(chapter):
        return AccessDecision(
            allowed=False, status="not_translated", label="Ещё не переведена",
            class_name="chapter-access-hidden", reason="missing_translation_date",
            required_role=required_role, viewer_role=role,
        )

    if not chapter_has_real_source(chapter):
        return AccessDecision(
            allowed=False, status="no_content_source", label="Глава пока недоступна",
            class_name="chapter-access-hidden", reason="missing_telegraph_source",
            required_role=required_role, viewer_role=role,
        )

    traveler_url = chapter_traveler_url(chapter, novel)
    guest_free_url = chapter_guest_free_url(chapter, novel)
    keeper_url = chapter_keeper_url(chapter, novel)
    traveler_date = _scheduled_date_for_role(chapter, "traveler")
    keeper_date = _scheduled_date_for_role(chapter, "keeper")

    # В 🎁-новелле гостю продаётся только тот уровень, который открывает
    # выбранную главу: 🌱 для основного диапазона, 📜 для ранней Keeper-главы.
    if is_gift_novel and role == "guest":
        if traveler_url:
            return AccessDecision(
                allowed=False, status="book_access_denied", label="Нужен 🌱",
                class_name="chapter-access-locked", reason="gift_novel_requires_traveler",
                required_role="traveler", viewer_role=role, release_date=traveler_date,
            )
        if keeper_url:
            return AccessDecision(
                allowed=False, status="free_scheduled", label="Доступ по 📜",
                class_name="chapter-access-locked", reason="gift_keeper_subscription_required",
                required_role="keeper", viewer_role=role, release_date=keeper_date,
            )
        return AccessDecision(
            allowed=False, status="premium_scheduled", label="Пока закрыта",
            class_name="chapter-access-locked", reason="outside_novel_status_boundary",
            required_role="traveler", viewer_role=role, release_date=traveler_date,
        )

    if profile.get("has_full_book_access") and not is_gift_novel:
        url = chapter_premium_url(chapter) or chapter_public_url(chapter)
        if url:
            return AccessDecision(
                allowed=True, status="full_book_entitlement", url=url, label="Открыта",
                class_name="chapter-access-public", reason="full_book_entitlement",
                required_role=required_role, viewer_role=role,
                release_date=keeper_date or traveler_date,
            )

    if is_gift_novel:
        if role == "keeper" and keeper_url:
            return AccessDecision(
                allowed=True, status="subscription_open", url=keeper_url,
                label="Открыта", class_name="chapter-access-subscription",
                reason="gift_keeper_novel_status", required_role="keeper",
                viewer_role=role, release_date=(keeper_date if not traveler_url else traveler_date),
            )
        if role in {"traveler", "keeper"} and traveler_url:
            return AccessDecision(
                allowed=True, status="subscription_open", url=traveler_url,
                label="Открыта", class_name="chapter-access-subscription",
                reason="gift_traveler_novel_status", required_role="traveler",
                viewer_role=role, release_date=traveler_date,
            )
        if role == "traveler" and keeper_url:
            return AccessDecision(
                allowed=False, status="free_scheduled", label="Доступ по 📜",
                class_name="chapter-access-locked", reason="gift_keeper_upgrade_available",
                required_role="keeper", viewer_role=role, release_date=keeper_date,
            )
        return AccessDecision(
            allowed=False, status="premium_scheduled", label="Пока закрыта",
            class_name="chapter-access-locked", reason="outside_novel_status_boundary",
            required_role=("keeper" if role == "keeper" else "traveler"),
            viewer_role=role, release_date=(keeper_date if role == "keeper" else traveler_date),
        )

    # У обычной новеллы бесплатный диапазон доступен всем, включая гостя
    # без единой подписки.  Проверяем его раньше Keeper-ветки, чтобы более
    # высокий уровень подписки не менял публичный источник главы.
    if guest_free_url:
        return AccessDecision(
            allowed=True, status="public_open", url=guest_free_url, label="Открыта",
            class_name="chapter-access-public", reason="free_chapter_for_everyone",
            required_role="guest", viewer_role=role, release_date=traveler_date,
        )

    # Для обычной новеллы 🌱 совпадает с бесплатным диапазоном.
    if role == "keeper" and keeper_url:
        keeper_only = not bool(traveler_url)
        return AccessDecision(
            allowed=True,
            status=("premium_open" if keeper_only else "public_open"),
            url=keeper_url,
            label="Открыта",
            class_name=("chapter-access-subscription" if keeper_only else "chapter-access-public"),
            reason=("keeper_novel_status" if keeper_only else "traveler_novel_status"),
            required_role=("keeper" if keeper_only else "guest"),
            viewer_role=role,
            release_date=(keeper_date if keeper_only else traveler_date),
        )

    if role in {"guest", "traveler"} and traveler_url:
        return AccessDecision(
            allowed=True, status="public_open", url=traveler_url, label="Открыта",
            class_name="chapter-access-public", reason="traveler_novel_status",
            required_role="guest", viewer_role=role, release_date=traveler_date,
        )

    keeper_upgrade_available = role != "keeper" and bool(keeper_url)
    return AccessDecision(
        allowed=False,
        status=("free_scheduled" if keeper_upgrade_available else "premium_scheduled"),
        label=("Доступ по 📜" if keeper_upgrade_available else "Пока закрыта"),
        class_name="chapter-access-locked",
        reason=("keeper_upgrade_available" if keeper_upgrade_available else "outside_novel_status_boundary"),
        required_role=("keeper" if keeper_upgrade_available or role == "keeper" else "guest"),
        viewer_role=role,
        release_date=(keeper_date if keeper_upgrade_available or role == "keeper" else traveler_date),
    )

def decide_chapter_access(chapter: dict, novel: dict, profile: dict[str, Any]) -> AccessDecision:
    return enrich_access_decision(_decide_chapter_access_raw(chapter, novel, profile), chapter, novel, profile)

def chapter_content_url_for_access(chapter: dict, novel: dict, profile: dict[str, Any]) -> str:
    """Return the only URL the current user may receive."""
    return decide_chapter_access(chapter, novel, profile).url
