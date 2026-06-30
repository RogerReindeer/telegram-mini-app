from __future__ import annotations

from typing import Any
from .. import database
from ..config import settings
from ..utils import clean, parse_tags, slugify, to_bool, to_int, is_open_date


def _field(row: dict[str, Any], *names: str, default: Any = '') -> Any:
    lower = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name in row and row[name] not in (None, ''):
            return row[name]
        key = name.lower()
        if key in lower and lower[key] not in (None, ''):
            return lower[key]
    return default


def _tag_items(tags: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tag in tags[:14]:
        is_rating = tag.replace(' ', '').lower() in {'18+', '18'}
        result.append({
            'text': tag,
            'is_spoiler': False,
            'class_name': 'tag-rating' if is_rating else 'tag-soft',
        })
    return result


def adapt_novel(row: dict[str, Any]) -> dict[str, Any]:
    novel_id = to_int(_field(row, 'id', 'novel_id', 'NovelID'))
    title = clean(_field(row, 'title_ru', 'display_title', 'title', 'Title RU', 'NovelShort'), 'Без названия')
    short = clean(_field(row, 'library_short_title', 'short_title', 'NovelShort'), title)
    slug = clean(_field(row, 'slug', 'code', 'Code'), slugify(f'{novel_id}-{short}'))
    tags = parse_tags(_field(row, 'tags', 'NovelTag', 'tag_list'))
    age_rating = clean(_field(row, 'age_rating')) or ('18+' if any(t.replace(' ', '') == '18+' for t in tags) else '')
    status_raw = clean(_field(row, 'translation_status', 'status', 'Status'), 'active')
    status_label = 'Завершено' if '✅' in status_raw or status_raw.lower() in {'done', 'complete', 'completed'} else status_raw.replace('🛠', 'В работе').replace('⏳', 'Скоро')
    access_model = clean(_field(row, 'access_model', 'AccessModel'))
    is_subscriber = 'boosty' in access_model.lower() or 'gift' in access_model.lower() or '🎁' in access_model
    translated = to_int(_field(row, 'translated_chapters', 'TranslatedChapters'))
    total = to_int(_field(row, 'total_chapters', 'TotalChapters'), translated)
    free_count = to_int(_field(row, 'free_chapters_count'), 0)
    keeper_count = to_int(_field(row, 'keeper_chapters_count'), free_count)
    state_class = 'is-subscriber' if is_subscriber else ('is-complete' if 'Завершено' in status_label else 'is-startable')
    return {
        **row,
        'id': novel_id,
        'slug': slug,
        'display_title': title,
        'library_short_title': short,
        'library_secondary_title': clean(_field(row, 'title_en', 'Title EN')),
        'description': clean(_field(row, 'description', 'Примечание')),
        'description_paragraphs': [clean(_field(row, 'description', 'Примечание'))] if clean(_field(row, 'description', 'Примечание')) else [],
        'cover_url': clean(_field(row, 'cover_url', 'cover', 'CoverURL')),
        'age_rating': age_rating,
        'translation_status': 'done' if 'Завершено' in status_label else 'active',
        'translation_status_label': status_label or 'В работе',
        'translation_status_color': '#75a878',
        'show_access_badge': is_subscriber,
        'access_badge': {'icon': '💛', 'label': 'Для подписчиков'} if is_subscriber else None,
        'free_chapters_count': free_count,
        'keeper_chapters_count': keeper_count,
        'translated_chapters': translated,
        'total_chapters': total,
        'catalog_tag_items': _tag_items(tags),
        'card_tag_items': _tag_items(tags),
        'card_state_class': state_class,
        'is_hidden': to_bool(_field(row, 'is_hidden', 'hidden')),
        'top_description': clean(_field(row, 'top_description')),
        'bottom_description': clean(_field(row, 'bottom_description')),
    }


def adapt_chapter(row: dict[str, Any]) -> dict[str, Any]:
    chapter_id = clean(_field(row, 'chapter_id', 'ChapterID', 'id'))
    public_date = _field(row, 'free_release_date', 'FreeReleaseDate')
    keeper_date = _field(row, 'premium_release_date', 'PremiumReleaseDate')
    required = clean(_field(row, 'required_role', 'access_role'), 'guest')
    is_available = required in {'', 'guest'} and is_open_date(public_date)
    return {
        **row,
        'chapter_id': chapter_id,
        'display_title': clean(_field(row, 'display_title', 'title', 'ChapterTitle'), f'Глава {chapter_id}'),
        'source_chapter_no': _field(row, 'source_chapter_no', 'SourceChapterNo', 'chapter_no', 'ChapterNo'),
        'part_no': _field(row, 'part_no', 'PartNo'),
        'volume_title': clean(_field(row, 'volume_title', 'VolumeTitle')),
        'volume_no': _field(row, 'volume_no', 'VolumeNo'),
        'volume': clean(_field(row, 'volume')),
        'is_available': is_available,
        'required_role': 'keeper' if required == 'keeper' or keeper_date else required,
        'access_label': 'Открыта' if is_available else ('Откроется позже' if public_date else 'Для подписчиков'),
        'access_class': 'chapter-access-open' if is_available else 'chapter-access-locked',
        'is_paid_extra': False,
        'sort_value': to_int(_field(row, 'chapter_no', 'ChapterNo'), 999999),
    }


def get_fox() -> dict[str, str]:
    return {}


def get_novels() -> list[dict[str, Any]]:
    rows = database.select('novels', {'select': '*'})
    return [adapt_novel(row) for row in rows]


def get_novel(slug: str) -> dict[str, Any] | None:
    rows = database.select('novels', {'select': '*', 'slug': f'eq.{slug}', 'limit': '1'})
    if not rows:
        rows = database.select('novels', {'select': '*', 'code': f'eq.{slug}', 'limit': '1'})
    return adapt_novel(rows[0]) if rows else None


def get_chapters(novel_id: int) -> list[dict[str, Any]]:
    rows = database.select('chapters', {'select': '*', 'novel_id': f'eq.{novel_id}', 'order': 'chapter_no.asc'})
    return [adapt_chapter(row) for row in rows]


def get_chapter(chapter_id: str) -> dict[str, Any] | None:
    rows = database.select('chapters', {'select': '*', 'chapter_id': f'eq.{chapter_id}', 'limit': '1'})
    return adapt_chapter(rows[0]) if rows else None


def demo_novels() -> list[dict[str, Any]]:
    return [adapt_novel({
        'NovelID': 2,
        'Code': 'zlobny-master',
        'NovelShort': 'Злобный мастер',
        'Title RU': 'Злобный мастер',
        'Status': '✅ Завершено',
        'NovelTag': 'Даньмэй, Сянься/Уся, Перерождение, 18+',
        'TranslatedChapters': 253,
        'TotalChapters': 253,
        'description': 'Миниатюрный пример карточки для локальной проверки верстки без подключения Supabase.',
        'cover_url': '',
    })]


def demo_chapters(novel_id: int) -> list[dict[str, Any]]:
    return [adapt_chapter({'ChapterID': f'{novel_id}-1', 'ChapterNo': 1, 'ChapterTitle': 'Глава 1', 'required_role': 'guest'})]
