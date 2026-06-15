import csv
import os
from datetime import datetime
from io import StringIO
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

MINIAPP_SHEET_ID = os.getenv(
    "MINIAPP_SHEET_ID",
    "1-dHdJEnBai_ZAcdZKwgTryoQ-uAfSgP52qTnbU4amHs",
)

SYNC_TOKEN = os.getenv("SYNC_TOKEN")

app = FastAPI(title="Zefirki Reader Mini App")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# -----------------------------
# Supabase
# -----------------------------

def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY is not set")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_admin_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_KEY is not set")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# -----------------------------
# Helpers
# -----------------------------

def clean_value(value):
    if value is None:
        return ""
    return str(value).strip()


def to_int(value):
    value = clean_value(value)
    if not value:
        return None

    try:
        return int(float(value.replace(",", ".")))
    except ValueError:
        return None


def to_float(value):
    value = clean_value(value).replace("%", "").replace(",", ".")
    if not value:
        return None

    try:
        return float(value)
    except ValueError:
        return None


def to_bool(value):
    value = clean_value(value).lower()
    return value in ("true", "1", "yes", "да", "истина", "✅")


def normalize_date(value):
    value = clean_value(value)
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            pass

    return None


# -----------------------------
# Google Sheets → Supabase sync
# -----------------------------

def fetch_miniapp_sheet(sheet_name: str) -> list[dict]:
    url = (
        f"https://docs.google.com/spreadsheets/d/{MINIAPP_SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={sheet_name}"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    text = response.content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))

    return list(reader)


def sync_novels_to_db(db: Client) -> int:
    rows = fetch_miniapp_sheet("Novels")
    payload = []

    for row in rows:
        novel_id = to_int(row.get("NovelID"))

        if not novel_id:
            continue

        is_visible = to_bool(row.get("IsVisible"))

        payload.append({
            "id": novel_id,
            "code": clean_value(row.get("Code")),
            "slug": clean_value(row.get("Slug")) or f"novel-{novel_id}",
            "title": clean_value(row.get("Title")) or f"Novel {novel_id}",
            "title_en": clean_value(row.get("TitleEN")),
            "cover_url": clean_value(row.get("CoverURL")),
            "description": clean_value(row.get("Description")),
            "tags": clean_value(row.get("Tags")),
            "original_language": clean_value(row.get("OriginalLanguage")),
            "total_chapters": to_int(row.get("TotalChapters")),
            "translated_chapters": to_int(row.get("TranslatedChapters")),
            "progress_percent": to_float(row.get("ProgressPercent")),
            "status": clean_value(row.get("Status")),
            "access_model": clean_value(row.get("AccessModel")),
            "schedule_mode": clean_value(row.get("ScheduleMode")),
            "sort_order": to_float(row.get("SortOrder")) or novel_id,
            "is_visible": is_visible,
            "is_active": is_visible,
        })

    if payload:
        db.table("novels").upsert(payload, on_conflict="id").execute()

    return len(payload)


def sync_chapters_to_db(db: Client) -> int:
    rows = fetch_miniapp_sheet("Chapters")
    payload = []

    for row in rows:
        chapter_code = clean_value(row.get("ChapterID"))
        novel_id = to_int(row.get("NovelID"))
        chapter_no = to_float(row.get("ChapterNo"))
        telegraph_url = clean_value(row.get("TelegraphURL"))
        access_level = clean_value(row.get("AccessLevel")) or "reader"

        if not chapter_code or not novel_id or chapter_no is None:
            continue

        is_visible = to_bool(row.get("IsVisible"))

        free_url = telegraph_url if access_level == "reader" else ""
        premium_url = telegraph_url if access_level in ("boosty", "early") else ""

        payload.append({
            "chapter_code": chapter_code,
            "novel_id": novel_id,
            "chapter_no": chapter_no,
            "title": clean_value(row.get("ChapterTitle")) or f"Глава {chapter_no:g}",
            "slug": clean_value(row.get("Slug")) or f"chapter-{chapter_no:g}",
            "access_level": access_level,
            "release_date": normalize_date(row.get("ReleaseDate")),
            "telegraph_url": telegraph_url,
            "free_url": free_url,
            "premium_url": premium_url,
            "source_type": clean_value(row.get("SourceType")) or "telegraph",
            "is_visible": is_visible,
            "is_active": is_visible,
            "sort_order": to_float(row.get("SortOrder")) or chapter_no,
        })

    if payload:
        db.table("chapters").upsert(payload, on_conflict="chapter_code").execute()

    return len(payload)


def sync_miniapp_sheets_to_db() -> dict:
    db = get_admin_supabase()

    novels_count = sync_novels_to_db(db)
    chapters_count = sync_chapters_to_db(db)

    return {
        "status": "ok",
        "novels": novels_count,
        "chapters": chapters_count,
    }


# -----------------------------
# Telegraph
# -----------------------------

def normalize_telegraph_url(url: str) -> str:
    url = clean_value(url)

    if not url:
        raise HTTPException(status_code=404, detail="Telegraph URL is empty")

    if url.startswith("http://"):
        url = "https://" + url.removeprefix("http://")

    if not url.startswith("https://"):
        url = "https://" + url

    parsed = urlparse(url)

    if parsed.netloc != "telegra.ph":
        raise HTTPException(status_code=400, detail="Only telegra.ph links are allowed")

    return url


def clean_telegraph_article(article):
    stop_phrases = [
        "тгк зефиркины баоцзы",
        "зефиркины баоцзы",
        "спасибо, что читаете",
        "спасибо что читаете",
        "полный перевод",
        "доступен на бусти",
        "доступен на boosty",
        "boosty",
        "бусти",
        "bllate",
        "bl late",
        "bl-late",
    ]

    content_tags = article.find_all(["p", "div", "blockquote", "h3", "h4", "a"])

    for tag in content_tags:
        text = tag.get_text(" ", strip=True).lower()

        if any(phrase in text for phrase in stop_phrases):
            current = tag

            while current:
                next_tag = current.find_next_sibling()
                current.decompose()
                current = next_tag

            break

    return article


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

    for tag in article.select("address, aside, script, style"):
        tag.decompose()

    first_h1 = article.find("h1")
    if first_h1:
        first_h1.decompose()

    first_h2 = article.find("h2")
    if first_h2:
        first_h2.decompose()

    article = clean_telegraph_article(article)

    return {
        "source_url": url,
        "content_html": str(article),
    }


# -----------------------------
# Routes
# -----------------------------

@app.get("/", response_class=HTMLResponse)
async def home():
    return RedirectResponse(url="/library", status_code=302)


@app.get("/library", response_class=HTMLResponse)
async def library(request: Request):
    db = get_supabase()

    result = (
        db.table("novels")
        .select("*")
        .eq("is_visible", True)
        .order("sort_order")
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
        .eq("is_visible", True)
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
        .eq("is_visible", True)
        .order("sort_order")
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
        .eq("is_visible", True)
        .limit(1)
        .execute()
    )

    chapters = chapter_result.data or []

    if not chapters:
        raise HTTPException(status_code=404, detail="Chapter not found")

    chapter = chapters[0]

    telegraph_url = (
        chapter.get("telegraph_url")
        or chapter.get("free_url")
        or chapter.get("premium_url")
        or ""
    )

    telegraph_content = None

    if telegraph_url:
        telegraph_content = fetch_telegraph_article(telegraph_url)

    return templates.TemplateResponse(
        request,
        "chapter.html",
        {
            "app_title": "Зефиркины баоцзы",
            "chapter": chapter,
            "telegraph_content": telegraph_content,
        },
    )


@app.post("/admin/sync-from-sheets")
async def admin_sync_from_sheets(request: Request):
    if not SYNC_TOKEN:
        raise HTTPException(status_code=500, detail="SYNC_TOKEN is not set")

    token = request.headers.get("X-Sync-Token")

    if token != SYNC_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid sync token")

    return sync_miniapp_sheets_to_db()


@app.get("/health")
async def health():
    return {"status": "ok"}
