from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

APP_TITLE = "Зефиркины баоцзы"
APP_VERSION = "v111-design-polish-local"
BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title=APP_TITLE, version=APP_VERSION)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def asset(name: str) -> str:
    return f"/static/{name}"


FOX: dict[str, str] = {
    "fox_pic": asset("fox.svg"),
    "fox_sitting_front": asset("fox.svg"),
    "fox_sleeping": asset("fox.svg"),
    "fox_heart": asset("fox.svg"),
    "fox_side": asset("fox.svg"),
    "fox_laying_paws": asset("fox.svg"),
    "fox_peek": asset("fox.svg"),
    "fox_peek_left": asset("fox.svg"),
    "fox_peek_right": asset("fox.svg"),
}

VIEWER: dict[str, Any] = {
    "telegram_user_id": None,
    "role": "guest",
    "role_label": "Гость",
}

NOVELS: list[dict[str, Any]] = [
    {
        "id": 1,
        "slug": "lotosinka",
        "display_title": "После перерождения я снова встретил белый лотос",
        "library_short_title": "Лотосинка",
        "library_secondary_title": "После перерождения я снова встретил белый лотос",
        "cover_url": asset("cover-lotus.svg"),
        "age_rating": "18+",
        "translation_status": "active",
        "translation_status_label": "🛠 В работе",
        "translation_status_color": "#6f9b72",
        "show_access_badge": True,
        "access_badge": {"icon": "🌱", "label": "Boosty"},
        "free_chapters_count": 3,
        "keeper_chapters_count": 5,
        "translated_chapters": 7,
        "total_chapters": 82,
        "description_paragraphs": [
            "Мягкая сянься-история с интригами, долгими взглядами и героями, которые явно знают больше, чем говорят.",
            "В демо-версии этот текст нужен только для проверки дизайна оглавления, раскрытия описания и карточек глав.",
        ],
        "top_description": "Сдержанный, опасно внимательный и слишком хорошо помнит старые долги.",
        "bottom_description": "На первый взгляд мягкий, но за этой мягкостью прячется характер.",
        "catalog_tag_items": [
            {"text": "Сянься/Уся", "class_name": "tag-main", "is_spoiler": False},
            {"text": "Перерождение", "class_name": "tag-soft", "is_spoiler": False},
            {"text": "Медленное сближение", "class_name": "tag-soft", "is_spoiler": False},
            {"text": "Интриги", "class_name": "tag-warning", "is_spoiler": False},
        ],
    },
    {
        "id": 2,
        "slug": "zlobny-master",
        "display_title": "Злобный мастер никак не может стать хорошим человеком",
        "library_short_title": "Злобный мастер",
        "library_secondary_title": "Злобный мастер никак не может стать хорошим человеком",
        "cover_url": asset("cover-master.svg"),
        "age_rating": "18+",
        "translation_status": "done",
        "translation_status_label": "✅ Завершено",
        "translation_status_color": "#c99a45",
        "show_access_badge": True,
        "access_badge": {"icon": "📜", "label": "Хранитель"},
        "free_chapters_count": 4,
        "keeper_chapters_count": 6,
        "translated_chapters": 8,
        "total_chapters": 253,
        "description": "Комедийная история с вредным наставником, который слишком хорошо умеет делать вид, что ему всё равно.",
        "top_description": "Опасный, язвительный, любит контролировать ситуацию.",
        "bottom_description": "Упрямый, верный и подозрительно быстро привыкает к чужой заботе.",
        "catalog_tag_items": [
            {"text": "Система", "class_name": "tag-main", "is_spoiler": False},
            {"text": "Наставник/Ученик", "class_name": "tag-soft", "is_spoiler": False},
            {"text": "Комедия", "class_name": "tag-soft", "is_spoiler": False},
        ],
    },
    {
        "id": 3,
        "slug": "snake-bride",
        "display_title": "Брошенный командой, я стал невестой босса-змея",
        "library_short_title": "Невеста змея",
        "library_secondary_title": "Брошенный командой, я стал невестой босса-змея",
        "cover_url": asset("cover-snake.svg"),
        "age_rating": "18+",
        "translation_status": "active",
        "translation_status_label": "🛠 В работе",
        "translation_status_color": "#6f9b72",
        "show_access_badge": True,
        "access_badge": {"icon": "🎁", "label": "Бонус"},
        "free_chapters_count": 2,
        "keeper_chapters_count": 4,
        "translated_chapters": 6,
        "total_chapters": 7,
        "description": "Короткая бонусная история: немного опасности, немного нежности и один змей, который явно не собирается отпускать своё.",
        "top_description": "Бай Куй — спокойный, сильный и очень собственнический.",
        "bottom_description": "Линь Ци — живой, колкий и не так беспомощен, как кажется.",
        "catalog_tag_items": [
            {"text": "Фэнтези", "class_name": "tag-main", "is_spoiler": False},
            {"text": "Змей", "class_name": "tag-soft", "is_spoiler": False},
            {"text": "Бонус", "class_name": "tag-warning", "is_spoiler": False},
        ],
    },
]

CHAPTERS: dict[int, list[dict[str, Any]]] = {
    1: [
        {"chapter_id": "1-1", "display_title": "Глава 1. Возвращение", "access_label": "🌱 Открыто", "access_class": "chapter-access-free", "required_role": "guest", "is_available": True, "is_paid_extra": False, "sort_value": 1, "source_chapter_no": 1, "part_no": None, "volume_title": "Том 1"},
        {"chapter_id": "1-2", "display_title": "Глава 2. Старые долги", "access_label": "🌱 Открыто", "access_class": "chapter-access-free", "required_role": "guest", "is_available": True, "is_paid_extra": False, "sort_value": 2, "source_chapter_no": 2, "part_no": None},
        {"chapter_id": "1-3", "display_title": "Глава 3. Слишком знакомый взгляд", "access_label": "🌱 Открыто", "access_class": "chapter-access-free", "required_role": "guest", "is_available": True, "is_paid_extra": False, "sort_value": 3, "source_chapter_no": 3, "part_no": None},
        {"chapter_id": "1-4", "display_title": "Глава 4. Цветок в снегу", "access_label": "📜 Хранитель", "access_class": "chapter-access-keeper", "required_role": "keeper", "is_available": False, "is_paid_extra": False, "sort_value": 4, "source_chapter_no": 4, "part_no": None},
        {"chapter_id": "1-5", "display_title": "Глава 5. Откроется позже", "access_label": "Откроется 10.02.2027", "access_class": "chapter-access-scheduled", "required_role": "scheduled", "is_available": False, "is_paid_extra": True, "sort_value": 5, "source_chapter_no": 5, "part_no": None},
    ],
    2: [
        {"chapter_id": "2-1", "display_title": "Глава 1. Наставник не виноват", "access_label": "🌱 Открыто", "access_class": "chapter-access-free", "required_role": "guest", "is_available": True, "is_paid_extra": False, "sort_value": 1, "source_chapter_no": 1, "part_no": None, "volume_title": "Основная история"},
        {"chapter_id": "2-2", "display_title": "Глава 2. Очень плохой план", "access_label": "🌱 Открыто", "access_class": "chapter-access-free", "required_role": "guest", "is_available": True, "is_paid_extra": False, "sort_value": 2, "source_chapter_no": 2, "part_no": None},
        {"chapter_id": "2-52-1", "display_title": "Глава 52. Часть 1", "access_label": "🌱 Открыто", "access_class": "chapter-access-free", "required_role": "guest", "is_available": True, "is_paid_extra": False, "sort_value": 52, "source_chapter_no": 52, "part_no": 1},
        {"chapter_id": "2-52-2", "display_title": "Глава 52. Часть 2", "access_label": "📜 Хранитель", "access_class": "chapter-access-keeper", "required_role": "keeper", "is_available": False, "is_paid_extra": False, "sort_value": 53, "source_chapter_no": 52, "part_no": 2},
    ],
    3: [
        {"chapter_id": "3-1", "display_title": "Глава 1. В тени", "access_label": "🌱 Открыто", "access_class": "chapter-access-free", "required_role": "guest", "is_available": True, "is_paid_extra": False, "sort_value": 1, "source_chapter_no": 1, "part_no": None},
        {"chapter_id": "3-2", "display_title": "Глава 2. Невеста", "access_label": "🌱 Открыто", "access_class": "chapter-access-free", "required_role": "guest", "is_available": True, "is_paid_extra": False, "sort_value": 2, "source_chapter_no": 2, "part_no": None},
        {"chapter_id": "3-3", "display_title": "Глава 3. Чужая территория", "access_label": "📜 Хранитель", "access_class": "chapter-access-keeper", "required_role": "keeper", "is_available": False, "is_paid_extra": False, "sort_value": 3, "source_chapter_no": 3, "part_no": None},
    ],
}

CHAPTER_BODY = """
<p>Это демонстрационная глава для проверки дизайна читалки. Здесь важны не сюжетные детали, а то, как текст ложится на экран, насколько спокойно читаются абзацы и не мешают ли кнопки.</p>
<p>Читателю не нужно разбираться, где он находится: сверху видно название, снизу есть простая навигация, а текст остаётся главным элементом страницы.</p>
<p>Если открыть эту страницу в Telegram WebView или обычном мобильном браузере, можно проверить ширину, отступы, тёмную тему и поведение длинных абзацев.</p>
<p>Финальный интерфейс должен ощущаться мягким и собранным: без технического шума, без лишних кнопок и без ощущения, что это временная заглушка.</p>
"""


def find_novel_by_slug(slug: str) -> dict[str, Any] | None:
    return next((novel for novel in NOVELS if novel["slug"] == slug), None)


def find_chapter(chapter_id: str) -> tuple[dict[str, Any], dict[str, Any], int] | None:
    for novel in NOVELS:
        chapters = CHAPTERS.get(novel["id"], [])
        for index, chapter in enumerate(chapters):
            if chapter["chapter_id"] == chapter_id:
                return novel, chapter, index
    return None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {"status": "ready", "app_version": APP_VERSION, "mode": "local_design_demo"}


@app.get("/version")
def version() -> dict[str, Any]:
    return {
        "app_title": APP_TITLE,
        "app_version": APP_VERSION,
        "assets": ["style.css", "design-polish.css", "settings.js"],
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "app_title": APP_TITLE, "fox": FOX, "error": None},
    )


@app.get("/library", response_class=HTMLResponse)
def library(request: Request) -> HTMLResponse:
    continue_item = {
        "novel_title": "Лотосинка",
        "chapter_title": "Глава 2. Старые долги",
        "chapter_id": "1-2",
    }
    return templates.TemplateResponse(
        "library.html",
        {
            "request": request,
            "app_title": APP_TITLE,
            "fox": FOX,
            "viewer": VIEWER,
            "novels": NOVELS,
            "continue_item": continue_item,
        },
    )


@app.get("/novel/{slug}", response_class=HTMLResponse)
def novel_page(request: Request, slug: str) -> HTMLResponse:
    novel = find_novel_by_slug(slug)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    chapters = CHAPTERS.get(novel["id"], [])
    hidden_subscriber_count = len([chapter for chapter in chapters if chapter.get("is_paid_extra")])
    return templates.TemplateResponse(
        "novel.html",
        {
            "request": request,
            "app_title": APP_TITLE,
            "fox": FOX,
            "viewer": VIEWER,
            "novel": novel,
            "chapters": chapters,
            "hidden_subscriber_count": hidden_subscriber_count,
        },
    )


@app.get("/chapter/{chapter_id}", response_class=HTMLResponse)
def chapter_page(request: Request, chapter_id: str) -> HTMLResponse:
    found = find_chapter(chapter_id)
    if not found:
        raise HTTPException(status_code=404, detail="Chapter not found")
    novel, chapter, index = found
    chapters = CHAPTERS.get(novel["id"], [])
    is_locked = not bool(chapter.get("is_available"))
    previous_chapter = chapters[index - 1] if index > 0 else None
    next_chapter = chapters[index + 1] if index + 1 < len(chapters) else None
    return templates.TemplateResponse(
        "chapter.html",
        {
            "request": request,
            "app_title": APP_TITLE,
            "fox": FOX,
            "viewer": VIEWER,
            "novel": novel,
            "chapter": chapter,
            "chapter_index": index,
            "available_chapters": len([item for item in chapters if item.get("is_available")]),
            "is_locked": is_locked,
            "telegraph_content": {"content_html": CHAPTER_BODY} if not is_locked else None,
            "telegraph_error": None,
            "preview_text": "Эта глава пока закрыта. Доступ проверяется через подписку Boosty.",
            "access_copy": {
                "title": "Глава ждёт доступа",
                "description": "Если подписка уже оформлена, нажмите проверку доступа. Если доступа ещё нет, его можно получить на Boosty.",
            },
            "boosty_access_url": "https://boosty.to/",
            "previous_chapter": previous_chapter,
            "next_chapter": next_chapter,
        },
    )


@app.exception_handler(404)
def not_found(request: Request, exc: HTTPException) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_title": APP_TITLE,
            "fox": FOX,
            "error": "Страница не найдена. Вернитесь в библиотеку.",
        },
        status_code=404,
    )
