import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = FastAPI(title="Zefirki Reader Mini App")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY is not set")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


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
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
