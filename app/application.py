from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .config import BASE_DIR, settings
from .assets import build_manifest, static_url
from .middleware import SecurityHeadersMiddleware, ResponseCacheHeadersMiddleware, RateLimitMiddleware
from .routers import system, catalog, user, auth, sync, admin, payments


def create_app() -> FastAPI:
    build_manifest()
    app = FastAPI(title=settings.app_title, version=settings.app_version)
    app.mount('/static', StaticFiles(directory=BASE_DIR / 'static'), name='static')
    templates = Jinja2Templates(directory=BASE_DIR / 'templates')
    templates.env.globals['static_url'] = static_url
    app.state.templates = templates

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ResponseCacheHeadersMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(system.router)
    app.include_router(catalog.router)
    app.include_router(user.router)
    app.include_router(auth.router)
    app.include_router(sync.router)
    app.include_router(admin.router)
    app.include_router(payments.router)

    @app.exception_handler(404)
    def not_found(request: Request, exc: HTTPException) -> HTMLResponse:
        from .services.catalog import get_fox
        return templates.TemplateResponse('index.html', {"request": request, "app_title": settings.app_title, "fox": get_fox(), "error": "Страница не найдена. Вернитесь в библиотеку."}, status_code=404)

    return app
