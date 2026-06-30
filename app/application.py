from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .assets import static_url
from .middleware import install_exception_handlers, install_middlewares
from .routers.admin import router as admin_router
from .routers.admin_page import create_admin_page_router
from .routers.auth import create_auth_router
from .routers.catalog import create_catalog_router
from .routers.payments import router as payments_router
from .routers.sync import router as sync_router
from .routers.system import router as system_router
from .routers.user import create_user_router
from .services.auth import public_viewer, require_authenticated_viewer
from .services.catalog import get_fox

SITE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(SITE_ROOT / ".env")

APP_TITLE = "Зефиркины баоцзы"

app = FastAPI(title="Zefirki Reader Mini App")
install_middlewares(app)
app.mount("/static", StaticFiles(directory=str(SITE_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(SITE_ROOT / "templates"))
templates.env.globals["static_url"] = static_url

app.include_router(system_router)
app.include_router(admin_router)
app.include_router(create_admin_page_router(templates=templates, app_title=APP_TITLE))
app.include_router(create_auth_router())
app.include_router(create_user_router(require_authenticated_viewer, public_viewer))
app.include_router(sync_router)
app.include_router(payments_router)
app.include_router(create_catalog_router(templates=templates, app_title=APP_TITLE))
install_exception_handlers(app, templates=templates, app_title=APP_TITLE, get_fox=get_fox)
