import csv
import os
from datetime import date, datetime
from io import StringIO
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

GOOGLE_SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID",
    "1ussa5hwhayj9Trzlz0GzSXHYkBUmul8FGdbmp-vfvHM",
)
GOOGLE_SHEET_GID = os.getenv("GOOGLE_SHEET_GID", "838963845")

app = FastAPI(title="Zefirki Reader Mini App")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY is not set")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_sheet_csv_url() -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&gid={GOOGLE_SHEET_GID}"
    )


def fetch_sheet_rows() -> list[dict]:
    url = get_sheet_csv_url()

    response = requests.get(url, timeout=20)
    response.raise_for_status()

    text = response.content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))

    return list(reader)


def find_chapter_in_sheet(novel_id: int, chapter_no: int) -> dict:
    rows = fetch_sheet_rows()

    for row in rows:
        try:
            row_novel_id = int(str(row.get("NovelID", "")).strip())
            row_chapter_no = int(float(str(row.get("ChapterNo", "")).strip()))
        except ValueError:
            continue

        if row_novel_id == novel_id and row_chapter_no == chapter_no:
            return row

    raise HTTPException(
        status_code=404,
        detail=f"Chapter not found in sheet: NovelID={novel_id}, ChapterNo={chapter_no}",
    )


def parse_date(value: str) -> date | None:
    value = (value or "").strip()

    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


def is_free_chapter_available(row: dict) -> bool:
    free_url = (row.get("TelegraphFreeURL") or "").strip()

    if not free_url:
        return False

    free_release_date = parse_date(row.get("FreeReleaseDate", ""))

    # Для теста можно пускать, если ссылка уже есть.
    # Когда включим полноценный доступ, здесь будем строго проверять дату и подписку.
    if free_release_date is None:
        return True

    return free_release_date <= date.today()


def normalize_telegraph_url(url: str) -> str:
    url = (url or "").strip()

    if not url:
        raise HTTPException(status_code=404, detail="Telegraph URL is empty")

    if url.startswith("http://"):
        url = "https://" + url.removeprefix("http://")

    if not url.startswith("https://"):
        url = "https://" + url

    parsed = urlparse(url)

    if parsed.netloc not in ("telegra.ph", "telegra.ph"):
        raise HTTPException(status_code=400, detail="Only telegra.ph links are allowed")

    return url


def fetch_telegraph_article(url: str) -> dict:
    url = normalize_telegraph_url(url)

    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 ZefirkiReader/1.0",
        },
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    article = soup.find("article")

    if not article:
        raise HTTPException(status_code=502, detail="Telegraph article not found")

    # Убираем служебные элементы Telegraph, если попадутся.
    for tag in article.select("address, aside, script, style"):
        tag.decompose()

    # Убираем заголовок внутри article, потому что свой заголовок мы выводим сами.
    first_h1 = article.find("h1")
    if first_h1:
        first_h1.decompose()

    first_h2 = article.find("h2")
    if first_h2:
        first_h2.decompose()

    content_html = str(article)

    return {
        "source_url": url,
        "content_html": content_html,
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_title": "Зефиркины баоцзы",
        },
    )


@app.get("/library", response_class=HTMLResponse)
async def library(request: Request):
    db = get_supabase()

    result = (
        db.table("novels")
        .select("*")
        .eq("is_active", True)
        .order("id")
        .execute()
    )

    novels = result.data or []

    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "app_title": "Зефиркины баоцзы",
            "novels": novels,
        },
    )


@app.get("/novel/{slug}", response_class=HTMLResponse)
async def novel_page(request: Request, slug: str):
    db = get_supabase()

    novel_result = (
        db.table("novels")
        .select("*")
        .eq("slug", slug)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    novels = novel_result.data or []

    if not novels:
        raise HTTPException(status_code=404, detail="Novel not found")

    novel = novels[0]

    chapters_result = (
        db.table("chapters")
        .select("*")
        .eq("novel_id", novel["id"])
        .eq("is_active", True)
        .order("chapter_no")
        .execute()
    )

    chapters = chapters_result.data or []

    return templates.TemplateResponse(
        request,
        "novel.html",
        {
            "app_title": "Зефиркины баоцзы",
            "novel": novel,
            "chapters": chapters,
        },
    )


@app.get("/chapter/{chapter_id}", response_class=HTMLResponse)
async def chapter_page(request: Request, chapter_id: int):
    db = get_supabase()

    chapter_result = (
        db.table("chapters")
        .select("*, novels(title, slug)")
        .eq("id", chapter_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    chapters = chapter_result.data or []

    if not chapters:
        raise HTTPException(status_code=404, detail="Chapter not found")

    chapter = chapters[0]

    return templates.TemplateResponse(
        request,
        "chapter.html",
        {
            "app_title": "Зефиркины баоцзы",
            "chapter": chapter,
            "telegraph_content": None,
        },
    )


@app.get("/chapter/{novel_id}/{chapter_no}", response_class=HTMLResponse)
async def chapter_from_sheet(request: Request, novel_id: int, chapter_no: int):
    row = find_chapter_in_sheet(novel_id=novel_id, chapter_no=chapter_no)

    if not is_free_chapter_available(row):
        raise HTTPException(
            status_code=403,
            detail="Chapter is not available in free access",
        )

    telegraph_url = (row.get("TelegraphFreeURL") or "").strip()

    if not telegraph_url:
        raise HTTPException(status_code=404, detail="TelegraphFreeURL is empty")

    telegraph_content = fetch_telegraph_article(telegraph_url)

    chapter = {
        "title": row.get("ChapterTitle") or f"Глава {chapter_no}",
        "chapter_no": chapter_no,
        "access_level": "reader",
        "free_url": telegraph_url,
        "novels": {
            "title": f"NovelID {novel_id}",
            "slug": f"sheet-{novel_id}",
        },
    }

    return templates.TemplateResponse(
        request,
        "chapter.html",
        {
            "app_title": "Зефиркины баоцзы",
            "chapter": chapter,
            "telegraph_content": telegraph_content,
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
