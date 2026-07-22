from __future__ import annotations

import re
from typing import Any

from ..utils import (
    clean_value,
    is_date_open,
    normalize_slug,
    normalize_progress_percent,
    parse_date,
    to_bool,
    to_float,
    to_int,
)
from .access import (
    access_copy,
    access_paywall_copy,
    can_view_novel_for_profile,
    chapter_toc_notice,
    chapter_content_url_for_access,
    chapter_content_url_for_role,
    chapter_is_translated,
    chapter_preview_url,
    chapter_public_ready,
    chapter_public_url,
    chapter_premium_ready,
    chapter_premium_url,
    decide_chapter_access,
    effective_role_for_novel,
    normalize_required_role,
    novel_is_gift,
    novel_is_traveler_only,
    novel_required_role,
    viewer_access_profile,
    viewer_can_access_required_role,
)


def split_tags(tags: Any) -> list[str]:
    text = clean_value(tags)
    if not text:
        return []
    return [clean_value(part) for part in re.split(r"[;,\n]+", text) if clean_value(part)]

def strip_leading_service_icons_from_title(title: Any) -> str:
    title_text = clean_value(title)
    return re.sub(r"^[\s💙❤️💚✅🛠⏳🟢🟡🔴🎁📗📖]+", "", title_text).strip()

def compact_title_with_icons(post_icons: Any, title: Any) -> str:
    title_text = clean_value(title)
    icons = clean_value(post_icons)
    if not title_text:
        return ""
    clean_title = strip_leading_service_icons_from_title(title_text) or title_text
    return f"{icons} {clean_title}".strip() if icons else clean_title

def tag_class_name(tag: str) -> str:
    text = clean_value(tag).replace("!", "").lower()
    if text in ("гет", "het"):
        return "tag-get"
    if text in ("слэш", "slash", "bl", "бл", "данмэй"):
        return "tag-slash"
    if text in ("джен", "gen", "нет любовной линии"):
        return "tag-gen"
    if text in ("китай", "корея", "япония"):
        return "tag-country"
    if text in ("g", "pg", "pg-13", "r", "16+", "18+", "21+", "nc-17"):
        return "tag-rating"
    if text in ("сянься/уся", "уся/сянься", "фэнтези", "романтика", "приключения", "хэ"):
        return "tag-genre"
    return ""

def normalize_visible_tag_text(tag: Any) -> str:
    """Return the user-facing tag text.

    Some Latin abbreviations are visually ambiguous in the current UI font.
    In particular, Latin ``HE`` looks like Cyrillic ``НЕ`` on tag chips, so
    show the localized fandom abbreviation ``ХЭ`` instead.
    """
    text = clean_value(tag)
    if not text:
        return ""

    alias_key = (
        text.strip()
        .lower()
        .replace("ё", "е")
        .replace("н", "h")
        .replace("е", "e")
        .replace("э", "e")
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )

    if alias_key in {"he", "happyending", "happyend"}:
        return "ХЭ"

    return text


def prepare_tag_items(tags: str) -> list[dict]:
    result = []
    for raw_tag in split_tags(tags):
        text = clean_value(raw_tag)
        is_spoiler = text.startswith("!")
        source_text = text[1:].strip() if is_spoiler else text
        shown_text = normalize_visible_tag_text(source_text)
        if shown_text:
            result.append({
                "text": shown_text,
                "source_text": source_text,
                "raw_text": text,
                "is_spoiler": is_spoiler,
                "class_name": tag_class_name(shown_text),
            })
    return result

def normalize_tag_text_for_priority(tag: Any) -> str:
    return clean_value(tag).replace("!", "").strip().lower()

def is_age_rating_tag(tag: Any) -> bool:
    return normalize_tag_text_for_priority(tag) in ("g", "pg", "pg-13", "r", "r18", "r-18", "nc-17", "16+", "18+", "21+")

def is_country_tag_for_library(tag: Any) -> bool:
    return normalize_tag_text_for_priority(tag) in ("китай", "корея", "япония", "англия", "сша")

def get_age_rating_from_tags(tags: str) -> str:
    for raw_tag in split_tags(tags):
        normalized = normalize_tag_text_for_priority(raw_tag)
        if normalized == "g":
            return "G"
        if normalized == "pg":
            return "PG"
        if normalized == "pg-13":
            return "PG-13"
        if normalized in ("r18", "r-18", "18+"):
            return "18+"
        if normalized == "16+":
            return "16+"
        if normalized == "21+":
            return "21+"
        if normalized == "nc-17":
            return "NC-17"
        if normalized == "r":
            return "R"
    return ""

def is_card_hidden_tag(tag: Any) -> bool:
    normalized = normalize_tag_text_for_priority(tag)
    hidden_tags = {
        "s", "m", "l", "мини", "миди", "макси", "💙", "❤️", "💚", "✅", "🛠", "⏳",
        "🟢", "🟡", "🔴", "🎁", "📗", "📖", "завершена", "завершено",
        "в процессе перевода", "переводится", "на передержке", "скоро", "часть платно",
        "частично платно", "платно", "boosty only",
        "ch", "cn", "zh", "ru", "en",
    }
    return normalized in hidden_tags

def tag_priority_score(tag: dict) -> int:
    text = normalize_tag_text_for_priority(tag.get("text"))
    if tag.get("is_spoiler"):
        return 999
    if is_age_rating_tag(text):
        return 998
    if text in {"гет", "слэш", "bl", "бл", "данмэй", "джен", "нет любовной линии"}:
        return 1
    if text in {"китай", "корея", "япония", "англия", "сша"}:
        return 2
    if text in {"pov героини", "pov героя", "pov пассива", "pov актива"}:
        return 3
    if text in {"сянься/уся", "уся/сянься", "фэнтези", "романтика", "приключения", "юмор", "детектив", "мистика/оккультизм", "магия", "звери", "зверолюди/оборотни", "реинкарнация/возрождение", "здоровые отношения", "хэ"}:
        return 4
    return 50

def build_card_tag_items(tag_items: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for item in tag_items:
        text = clean_value(item.get("text"))
        normalized = normalize_tag_text_for_priority(text)
        if not text or item.get("is_spoiler") or is_age_rating_tag(text) or is_card_hidden_tag(text) or normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
    return sorted(result, key=lambda item: (tag_priority_score(item), clean_value(item.get("text")).lower()))

def normalize_translation_status(raw_status: Any, raw_label: Any = "") -> str:
    text = f"{clean_value(raw_status)} {clean_value(raw_label)}".lower()
    if any(marker in text for marker in ("completed", "complete", "done", "заверш", "✅", "готов")):
        return "completed"
    if any(marker in text for marker in ("paused", "pause", "hold", "передерж", "пауза", "⏳")):
        return "paused"
    if any(marker in text for marker in ("soon", "анонс", "скоро")):
        return "soon"
    return "in_progress"

def translation_status_label(status: str, fallback: Any = "") -> str:
    fallback_text = clean_value(fallback)
    if fallback_text:
        return fallback_text
    return {"completed": "Завершено", "paused": "На паузе", "soon": "Скоро", "in_progress": "Переводится"}.get(status, "Переводится")

def translation_status_color(status: str, fallback: Any = "") -> str:
    fallback_text = clean_value(fallback)
    if fallback_text:
        return fallback_text
    return {"completed": "#44bb44", "paused": "#f59e0b", "soon": "#4f7cff", "in_progress": "#7c5cff"}.get(status, "#7c5cff")

def build_access_badge(access_model: Any, early_access_mode: Any = "") -> dict | None:
    text = f"{clean_value(access_model)} {clean_value(early_access_mode)}".lower()
    if not text.strip():
        return None
    if "boosty" in text or "boostyonly" in text or "🎁" in text:
        return {"icon": "🎁", "label": "Boosty only", "class_name": "access-boosty"}
    if "mini" in text or "🧲" in text:
        return {"icon": "🔴", "label": "Платно", "class_name": "access-paid"}
    if "auto" in text or "early" in text or "⏰" in text:
        return {"icon": "🟡", "label": "Часть платно", "class_name": "access-partial"}
    if "core" in text or "🌷" in text:
        return {"icon": "🟢", "label": "Через 🌱", "class_name": "access-core"}
    return {"icon": "🟡", "label": "Часть платно", "class_name": "access-partial"}

def parse_chapter_no_number(value: Any) -> float:
    text = clean_value(value).replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except ValueError:
        return 0.0

def normalize_chapter_no_for_unit(value: Any) -> str:
    text = clean_value(value).replace(",", ".").strip()
    if not text:
        return ""
    lowered = text.lower()
    for pattern in (r"^(\d+)[-–—_]\d+$", r"^(\d+)\.\d+$", r"^(\d+)\s*(?:часть|ч\.|part)\s*\d+$", r"^глава\s*(\d+)"):
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    match = re.search(r"\d+", text)
    return match.group(0) if match else text.lower()

def display_number(value: Any) -> str:
    """Preserve an original chapter number as readable text without .0 noise."""
    text = clean_value(value).replace(",", ".")
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text

def chapter_source_label(chapter: dict) -> str:
    source_no = display_number(chapter.get("source_chapter_no")) or display_number(chapter.get("chapter_no"))
    part_no = display_number(chapter.get("part_no"))
    label = f"Глава {source_no}" if source_no else "Глава"
    if part_no:
        label += f". Часть {part_no}"
    return label

def chapter_meaningful_title(chapter: dict) -> str:
    """Remove an old generic chapter prefix so the new original numbering is not duplicated."""
    title = clean_value(chapter.get("chapter_title") or chapter.get("title"))
    if not title:
        return ""
    cleaned = re.sub(
        r"^\s*глава\s*[\d.,-]+(?:\s*[.:-]\s*|\s+)",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(
        r"^\s*часть\s*\d+\s*[.:-]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    # Generic titles such as “Глава 12” contain no useful subtitle.
    if re.fullmatch(r"глава\s*[\d.,-]+", title, flags=re.IGNORECASE):
        return ""
    return cleaned or ""

def chapter_display_title(chapter: dict) -> str:
    label = chapter_source_label(chapter)
    subtitle = chapter_meaningful_title(chapter)
    return f"{label} — {subtitle}" if subtitle else label

def chapter_code_value(chapter: dict) -> str:
    return clean_value(chapter.get("chapter_code")) or clean_value(chapter.get("chapter_id"))

def chapter_unit_key(chapter: dict) -> str:
    # Every ChapterNo is a separate MiniApp reading unit, including parts.
    return chapter_code_value(chapter) or f"{clean_value(chapter.get('novel_id'))}:{clean_value(chapter.get('chapter_no'))}"

def chapter_has_readable_url(chapter: dict) -> bool:
    return bool(
        clean_value(chapter.get("telegraph_url"))
        or clean_value(chapter.get("telegraph_free_url"))
        or clean_value(chapter.get("telegraph_free_code"))
        or clean_value(chapter.get("telegraph_premium_url"))
        or clean_value(chapter.get("telegraph_premium_code"))
    )

def chapter_is_available(chapter: dict, viewer_role: str = "guest") -> bool:
    return bool(chapter_content_url_for_role(chapter, viewer_role))

def count_chapter_units_for_card(chapters: list[dict]) -> int:
    return len({chapter_unit_key(chapter) for chapter in chapters})

def count_available_chapter_units(chapters: list[dict], viewer_role: str = "guest") -> int:
    return len({chapter_unit_key(chapter) for chapter in chapters if chapter_is_available(chapter, viewer_role)})

def keeper_extra_chapter_limit_ids(chapters: list[dict], novel: dict, extra_count: int | None = None) -> set[str]:
    """Compatibility helper returning only access already stored in Supabase.

    ``extra_count`` is ignored intentionally: ReleaseSchedule is evaluated by
    MiniAppSync.gs, not by the website.
    """
    return {
        chapter_code_value(chapter)
        for chapter in chapters
        if chapter_public_ready(chapter) or chapter_premium_ready(chapter)
    }


def chapter_is_keeper_extra_blocked(
    chapter: dict, profile: dict[str, Any], keeper_allowed_ids: set[str] | None = None, novel: dict | None = None
) -> bool:
    if novel and novel_is_gift(novel):
        return False
    if clean_value(profile.get("role")) != "keeper" or profile.get("has_full_book_access"):
        return False
    if chapter_public_ready(chapter) or chapter_premium_ready(chapter):
        return False
    return chapter_is_translated(chapter) and chapter_has_readable_url(chapter)


def count_available_chapter_units_for_profile(
    chapters: list[dict], novel: dict, profile: dict[str, Any], keeper_allowed_ids: set[str] | None = None
) -> int:
    return len({
        chapter_unit_key(chapter)
        for chapter in chapters
        if chapter_content_url_for_access(chapter, novel, profile)
    })

def choose_chapter_url(chapter: dict, viewer_role: str = "guest") -> str:
    return chapter_content_url_for_role(chapter, viewer_role)

def prepare_chapter_for_template(chapter: dict, viewer_role: str = "guest") -> dict:
    prepared = dict(chapter)
    chapter_code = chapter_code_value(chapter)
    required_role = normalize_required_role(chapter.get("access_level"))
    prepared["id"] = chapter_code
    prepared["chapter_id"] = chapter_code
    prepared["chapter_code"] = chapter_code
    prepared["chapter_no"] = clean_value(chapter.get("chapter_no"))
    prepared["source_chapter_no"] = clean_value(chapter.get("source_chapter_no")) or prepared["chapter_no"]
    prepared["part_no"] = clean_value(chapter.get("part_no"))
    prepared["source_label"] = chapter_source_label(chapter)
    prepared["title"] = chapter_display_title(chapter)
    prepared["display_title"] = prepared["title"]
    prepared["required_role"] = required_role
    prepared["url"] = choose_chapter_url(chapter, viewer_role)
    prepared["is_available"] = bool(prepared["url"])
    prepared["viewer_role"] = viewer_role

    if prepared["is_available"]:
        # Не показываем пользователю, через какой именно уровень доступа
        # открылась глава. В интерфейсе достаточно нейтрального статуса.
        prepared["access_label"] = "Открыта"
        prepared["access_class"] = "chapter-access-public"
    elif required_role == "keeper":
        prepared["access_label"] = "📜 Хранитель свитков"
        prepared["access_class"] = "chapter-access-keeper"
    else:
        prepared["access_label"] = "⏳ Скоро откроется"
        prepared["access_class"] = "chapter-access-hidden"

    prepared["sort_value"] = to_float(chapter.get("sort_order"), parse_chapter_no_number(chapter.get("chapter_no")))
    return prepared

def sort_chapters(chapters: list[dict]) -> list[dict]:
    return sorted(chapters, key=lambda chapter: (to_float(chapter.get("sort_order"), parse_chapter_no_number(chapter.get("chapter_no"))), parse_chapter_no_number(chapter.get("chapter_no")), chapter_code_value(chapter)))

def build_chapter_display_list(chapters: list[dict], viewer_role: str = "guest") -> tuple[list[dict], int]:
    prepared = [
        prepare_chapter_for_template(chapter, viewer_role)
        for chapter in sort_chapters(chapters)
        if viewer_role == "keeper" or chapter.get("is_visible") is True
    ]

    # Показываем не более трёх закрытых глав как понятный предпросмотр.
    # Все доступные текущему пользователю главы остаются видимыми.
    locked_preview_limit = 3
    locked_seen = 0
    hidden_locked_count = 0

    for chapter in prepared:
        chapter["is_paid_extra"] = False
        chapter["hidden"] = False

        if chapter.get("is_available"):
            continue

        locked_seen += 1
        if locked_seen > locked_preview_limit:
            chapter["is_paid_extra"] = True
            chapter["hidden"] = True
            hidden_locked_count += 1

    return prepared, hidden_locked_count

def get_chapter_index_info(chapters: list[dict], current_chapter_id: str, viewer_role: str = "guest") -> dict:
    sorted_visible = [
        prepare_chapter_for_template(chapter, viewer_role)
        for chapter in sort_chapters(chapters)
        if chapter_is_available(chapter, viewer_role)
    ]
    units = []
    seen_units = set()
    for chapter in sorted_visible:
        key = chapter_unit_key(chapter)
        if key not in seen_units:
            seen_units.add(key)
            units.append({"unit_key": key, "chapter_id": chapter.get("chapter_id"), "chapter_title": chapter.get("title")})
    current_index = 0
    for index, unit in enumerate(units, start=1):
        if clean_value(unit.get("chapter_id")) == clean_value(current_chapter_id):
            current_index = index
            break
    return {"chapter_index": current_index, "available_chapters": len(units)}

def get_neighbor_chapters(chapters: list[dict], current_chapter_id: str, viewer_role: str = "guest") -> tuple[dict | None, dict | None]:
    available = [
        prepare_chapter_for_template(chapter, viewer_role)
        for chapter in sort_chapters(chapters)
        if chapter_is_available(chapter, viewer_role)
    ]
    index = next((i for i, chapter in enumerate(available) if clean_value(chapter.get("chapter_id")) == clean_value(current_chapter_id)), None)
    if index is None:
        return None, None
    previous_chapter = available[index - 1] if index > 0 else None
    next_chapter = available[index + 1] if index + 1 < len(available) else None
    return previous_chapter, next_chapter

def split_text_paragraphs(value: Any) -> list[str]:
    """Preserve paragraph breaks from the sheet instead of rendering a wall of text."""
    text = clean_value(value)

    if not text:
        return []

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)

    if "\n\n" in text:
        parts = re.split(r"\n\s*\n", text)
    else:
        parts = text.split("\n")

    paragraphs = []

    for part in parts:
        paragraph = re.sub(r"[ \t]+", " ", clean_value(part))

        if paragraph:
            paragraphs.append(paragraph)

    return paragraphs

def normalize_title_for_compare(value: Any) -> str:
    """Сравнивает названия без регистра, кавычек и декоративной пунктуации."""
    text = clean_value(value).casefold()
    # NovelShort и NovelTitleRu могут отличаться только кавычками, тире или
    # дополнительными пробелами. Для выбора второй строки это одно название.
    text = re.sub(r"[^0-9a-zа-яё]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()

def prepare_novel_for_template(novel: dict) -> dict:
    prepared = dict(novel)
    title = clean_value(novel.get("title"))
    secondary_title = clean_value(novel.get("title_en"))
    post_icons = clean_value(novel.get("post_icons"))
    tags = clean_value(novel.get("tags"))

    explicit_short_title = clean_value(
        novel.get("short_title")
        or novel.get("title_short")
        or novel.get("novel_short")
        or novel.get("short_name")
    )
    explicit_full_title = clean_value(
        novel.get("full_title")
        or novel.get("title_ru")
        or novel.get("novel_title_ru")
    )

    # В текущей схеме хранения:
    #   title    = NovelShort;
    #   title_en = нужная вторая строка библиотеки:
    #              NovelTitleRu, если оно отличается от короткого,
    #              NovelTitleEn, только если короткое и полное русские совпадают.
    # Поэтому английское название не показывается как обычная дополнительная строка.
    short_title = explicit_short_title or title
    stored_secondary_title = secondary_title
    stored_secondary_is_russian = bool(re.search(r"[А-Яа-яЁё]", stored_secondary_title))

    if explicit_full_title:
        full_title = explicit_full_title
    elif stored_secondary_is_russian:
        full_title = stored_secondary_title
    else:
        full_title = short_title

    english_title = clean_value(
        novel.get("english_title")
        or novel.get("novel_title_en")
        or novel.get("title_en_original")
        or (stored_secondary_title if stored_secondary_title and not stored_secondary_is_russian else "")
    )

    short_equals_full = bool(
        normalize_title_for_compare(short_title)
        and normalize_title_for_compare(short_title) == normalize_title_for_compare(full_title)
    )

    if explicit_full_title:
        library_secondary_title = english_title if short_equals_full else full_title
    else:
        # После синхронизации title_en уже содержит ровно ту вторую строку,
        # которая нужна карточке. Не пытаемся показывать английское название
        # в остальных случаях.
        library_secondary_title = stored_secondary_title

    tag_items = prepare_tag_items(tags)
    card_tag_items = build_card_tag_items(tag_items)
    toc_tag_items = [
        item
        for item in sorted(tag_items, key=lambda item: (tag_priority_score(item), clean_value(item.get("text")).lower()))
        if not is_age_rating_tag(item.get("text")) and not is_card_hidden_tag(item.get("text"))
    ]
    library_card_tag_items = [item for item in card_tag_items if not is_country_tag_for_library(item.get("text"))]
    translation_status = normalize_translation_status(novel.get("translation_status") or novel.get("status"), novel.get("translation_status_label"))
    progress_percent = normalize_progress_percent(novel.get("progress_percent"))
    prepared.update({
        "id": clean_value(novel.get("id")),
        "slug": clean_value(novel.get("slug")) or normalize_slug(title),
        "title": title,
        "display_title": compact_title_with_icons(post_icons, full_title or title),
        # В библиотеке главным становится NovelShort. Второй строкой показываем
        # NovelTitleRu, а при совпадении короткого и полного названий — NovelTitleEn.
        "library_short_title": compact_title_with_icons(post_icons, short_title or title),
        "library_full_title": full_title,
        "library_english_title": english_title,
        "library_secondary_title": library_secondary_title,
        # На странице оглавления английское название выводится только когда оно известно.
        "title_en": english_title,
        "post_icons": post_icons,
        "cover_url": clean_value(novel.get("cover_url")),
        "description": clean_value(novel.get("description")),
        "description_paragraphs": split_text_paragraphs(novel.get("description")),
        "top_description": clean_value(novel.get("top_description")),
        "bottom_description": clean_value(novel.get("bottom_description")),
        "tags": tags,
        "tag_items": tag_items,
        "toc_tag_items": toc_tag_items,
        "catalog_tag_items": card_tag_items[:6],
        "card_tag_items": card_tag_items[:6],
        "library_card_tag_items": library_card_tag_items[:6],
        "catalog_hidden_tags": max(0, len(library_card_tag_items) - 4),
        "age_rating": clean_value(novel.get("age_rating")) or get_age_rating_from_tags(tags),
        "total_chapters": to_int(novel.get("total_chapters"), 0),
        "translated_chapters": to_int(novel.get("translated_chapters"), 0),
        "free_chapters_count": to_int(novel.get("free_chapters_count") or novel.get("free_chapters"), 0),
        "traveler_chapters_count": to_int(novel.get("traveler_chapters_count") or novel.get("subscriber_chapters"), 0),
        "keeper_chapters_count": to_int(novel.get("keeper_chapters_count") or novel.get("keeper_chapters"), 0),
        "release_free_count": to_int(novel.get("release_free_count"), 0),
        "premium_lead_weeks": to_int(novel.get("premium_lead_weeks"), 0),
        "premium_count": to_int(novel.get("premium_count"), 0),
        "keeper_extra_chapters": to_int(novel.get("keeper_extra_chapters"), 0),
        "progress_percent": progress_percent,
        "normalized_progress_percent": progress_percent,
        "translation_status": translation_status,
        "translation_status_label": (
            "Скоро"
            if translation_status == "paused"
            else translation_status_label(translation_status, novel.get("translation_status_label"))
        ),
        "translation_status_color": translation_status_color(translation_status, novel.get("translation_status_color")),
        "access_badge": build_access_badge(novel.get("access_model"), novel.get("early_access_mode")),
        "relation_type": clean_value(novel.get("relation_type")),
        "relation_icon": clean_value(novel.get("relation_icon")),
        "relation_color": clean_value(novel.get("relation_color")),
        "sort_order": to_float(novel.get("sort_order"), 999999),
        "is_visible": to_bool(novel.get("is_visible"), True),
        "added_date": parse_date(novel.get("added_date")),
        "translation_author": clean_value(novel.get("translation_author")),
    })
    prepared["has_adult_badge"] = to_bool(novel.get("has_adult_badge"), False) or prepared["age_rating"] in ("18+", "21+", "NC-17", "R")
    prepared["display_chapters_count"] = to_int(novel.get("display_chapters_count"), prepared["total_chapters"])
    prepared["available_chapters_count"] = to_int(novel.get("available_chapters_count"), 0)
    return prepared


def stored_available_chapters_for_profile(novel: dict, profile: dict[str, Any] | None) -> int:
    """Map a viewer role to the counters already stored in Supabase.

    The MiniApp must never recount chapter rows for library/TOC counters. Those
    values are prepared by MiniAppSync.gs from the Excel Chapters sheet.
    """
    profile = profile or {}
    if profile.get("has_full_book_access"):
        return max(0, to_int(novel.get("translated_chapters"), 0))
    role = clean_value(profile.get("role")) or "guest"
    if role == "keeper":
        return max(0, to_int(novel.get("keeper_chapters_count") or novel.get("keeper_chapters"), 0))
    if role == "traveler":
        return max(0, to_int(novel.get("traveler_chapters_count") or novel.get("subscriber_chapters"), 0))
    return max(0, to_int(novel.get("free_chapters_count") or novel.get("free_chapters"), 0))

def finalize_novel_access_summary(prepared: dict) -> dict:
    """Подготавливает только значимые показатели доступа."""
    total = max(0, to_int(prepared.get("display_chapters_count"), 0))
    free_count = max(0, to_int(prepared.get("free_chapters_count"), 0))
    traveler_count = max(0, to_int(prepared.get("traveler_chapters_count"), 0))
    keeper_count = max(0, to_int(prepared.get("keeper_chapters_count"), 0))
    is_gift = bool(prepared.get("is_gift"))

    # В обычных книгах у Странствующего нет отдельного диапазона глав.
    # В подарочных 🎁 книгах любая подписка открывает саму книгу и её готовые
    # подписочные главы, поэтому traveler_count сохраняется отдельно.
    if not is_gift:
        traveler_count = free_count
    prepared["traveler_chapters_count"] = traveler_count

    all_free = total > 0 and free_count >= total
    show_free = free_count > 0
    show_traveler = is_gift and traveler_count > free_count
    show_keeper = keeper_count > max(free_count, traveler_count)
    boosty_paid_count = max(0, keeper_count - free_count)

    prepared["all_chapters_free"] = all_free
    prepared["show_free_stat"] = show_free
    prepared["show_traveler_stat"] = show_traveler
    prepared["show_keeper_stat"] = show_keeper
    prepared["boosty_paid_chapters_count"] = boosty_paid_count
    prepared["show_boosty_paid_stat"] = boosty_paid_count > 0
    prepared["show_access_badge"] = bool(prepared.get("access_badge")) and not all_free

    # Для полностью бесплатной новеллы не показываем «Платно»,
    # даже если в служебном поле AccessModel осталось старое значение.
    if all_free:
        prepared["access_badge"] = None

    return prepared

def attach_chapter_counts_to_novels(novels: list[dict], chapters: list[dict], viewer_role: str = "guest") -> list[dict]:
    """Backward-compatible wrapper that uses only Supabase novel counters."""
    result = []
    profile = {"role": viewer_role, "has_full_book_access": False}
    for novel in novels:
        prepared = prepare_novel_for_template(novel)
        prepared["is_gift"] = novel_is_gift(novel)
        prepared["required_role"] = "traveler" if prepared["is_gift"] else novel_required_role(novel)
        prepared["available_chapters_count"] = stored_available_chapters_for_profile(prepared, profile)
        prepared["viewer_has_book_access"] = viewer_can_access_required_role(viewer_role, prepared["required_role"])
        finalize_novel_access_summary(prepared)
        result.append(prepared)
    return result





def count_available_chapter_units_for_access(
    chapters: list[dict], novel: dict, profile: dict[str, Any]
) -> int:
    return count_available_chapter_units_for_profile(chapters, novel, profile)

def chapter_is_boosty_toc_row(chapter: dict, novel: dict, decision: Any) -> bool:
    """Return whether the TOC row should show the compact "Бусти" line.

    This is display-only. Access itself is still decided from the fields synced
    from Excel to Supabase. Publicly opened chapters never keep a Boosty label.
    """
    if decision.status in {"public_open", "not_translated", "no_content_source", "hidden"}:
        return False
    if chapter_public_ready(chapter):
        return False

    required_role = normalize_required_role(chapter.get("access_level"))
    return bool(
        novel_is_gift(novel)
        or chapter_premium_url(chapter)
        or to_bool(chapter.get("keeper_access"), False)
        or required_role in {"traveler", "keeper"}
    )


def prepare_chapter_for_access_template(
    chapter: dict, novel: dict, profile: dict[str, Any]
) -> dict:
    role = clean_value(profile.get("role")) or "guest"
    item = prepare_chapter_for_template(chapter, role)
    decision = decide_chapter_access(chapter, novel, profile)
    item["url"] = decision.url
    item["is_available"] = decision.allowed
    item["access_status"] = decision.status
    item["access_reason"] = decision.reason
    item["access_release_date"] = decision.release_date
    item["access_label"] = decision.label
    item["access_class"] = decision.class_name
    item["access_title"] = decision.title
    item["access_description"] = decision.description
    item["access_severity"] = decision.severity
    item["required_role"] = decision.required_role
    toc_notice = chapter_toc_notice(decision)
    item["is_boosty_chapter"] = chapter_is_boosty_toc_row(chapter, novel, decision)
    if item["is_boosty_chapter"]:
        toc_notice = {
            "label": "Бусти",
            "hint": "Глава относится к платному доступу Boosty",
            "class_name": "chapter-access-boosty",
        }
    item["toc_access_label"] = toc_notice.get("label", "")
    item["toc_access_hint"] = toc_notice.get("hint", "")
    item["toc_access_class"] = toc_notice.get("class_name", decision.class_name)
    item["has_toc_access_label"] = bool(item["toc_access_label"])
    return item

def build_chapter_display_list_for_access(
    chapters: list[dict], novel: dict, profile: dict[str, Any]
) -> tuple[list[dict], int]:
    role = clean_value(profile.get("role")) or "guest"
    prepared = []
    for chapter in sort_chapters(chapters):
        # Rows without any Telegraph content are service/planning rows, not TOC items.
        if not chapter_has_readable_url(chapter):
            continue
        if (
            chapter.get("is_visible") is not True
            and not novel_is_gift(novel)
            and role != "keeper"
            and not profile.get("has_full_book_access")
        ):
            continue
        item = prepare_chapter_for_access_template(chapter, novel, profile)
        prepared.append(item)

    locked_seen = 0
    hidden_locked_count = 0
    for item in prepared:
        item["is_paid_extra"] = False
        item["hidden"] = False
        if item.get("is_available"):
            continue
        locked_seen += 1
        if locked_seen > 3:
            item["is_paid_extra"] = True
            item["hidden"] = True
            hidden_locked_count += 1
    return prepared, hidden_locked_count

def get_chapter_index_info_for_access(
    chapters: list[dict], current_chapter_id: str, novel: dict, profile: dict[str, Any]
) -> dict:
    available = [
        prepare_chapter_for_access_template(chapter, novel, profile)
        for chapter in sort_chapters(chapters)
        if chapter_content_url_for_access(chapter, novel, profile)
    ]
    units = []
    seen_units = set()
    for chapter in available:
        key = chapter_unit_key(chapter)
        if key not in seen_units:
            seen_units.add(key)
            units.append({
                "unit_key": key,
                "chapter_id": chapter.get("chapter_id"),
                "chapter_title": chapter.get("title"),
            })
    current_index = next((i for i, unit in enumerate(units, 1)
                          if clean_value(unit.get("chapter_id")) == clean_value(current_chapter_id)), 0)
    return {
        "chapter_index": current_index,
        "available_chapters": stored_available_chapters_for_profile(novel, profile),
    }

def get_neighbor_chapters_for_access(
    chapters: list[dict], current_chapter_id: str, novel: dict, profile: dict[str, Any]
) -> tuple[dict | None, dict | None]:
    available = [
        prepare_chapter_for_access_template(chapter, novel, profile)
        for chapter in sort_chapters(chapters)
        if chapter_content_url_for_access(chapter, novel, profile)
    ]
    index = next((i for i, chapter in enumerate(available)
                  if clean_value(chapter.get("chapter_id")) == clean_value(current_chapter_id)), None)
    if index is None:
        return None, None
    return (available[index - 1] if index > 0 else None,
            available[index + 1] if index + 1 < len(available) else None)

def prepare_library_novels_for_access(
    novels: list[dict], chapters: list[dict], viewer: dict[str, Any] | None
) -> list[dict]:
    """Prepare cards from Supabase novel rows without recounting chapters."""
    viewer = viewer or {}
    result = []
    for novel in novels:
        novel_id_text = clean_value(novel.get("novel_id") or novel.get("id"))
        novel_id = to_int(novel_id_text, 0) or None
        if viewer.get("__fast_access_profile"):
            profile = dict(viewer.get("__fast_access_profile") or {})
            profile["novel_id"] = novel_id
        elif (clean_value(viewer.get("role")) in {"traveler", "keeper"}
                and not viewer.get("authenticated")
                and not viewer.get("user_id")):
            profile = {"role": clean_value(viewer.get("role")), "has_full_book_access": False}
        else:
            profile = viewer_access_profile(viewer, novel_id)
        if not can_view_novel_for_profile(novel, profile):
            continue

        prepared = prepare_novel_for_template(novel)
        prepared["is_gift"] = novel_is_gift(novel)
        prepared["required_role"] = "traveler" if prepared["is_gift"] else "guest"
        prepared["available_chapters_count"] = stored_available_chapters_for_profile(prepared, profile)
        prepared["viewer_has_book_access"] = can_view_novel_for_profile(novel, profile)
        prepared["viewer_has_full_book_access"] = bool(profile.get("has_full_book_access"))
        finalize_novel_access_summary(prepared)
        result.append(prepared)
    return result

