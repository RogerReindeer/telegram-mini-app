from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import settings

logger = logging.getLogger("zefirki.app")


API_PREFIXES = ("/api/", "/sync", "/health", "/ready", "/version")
SENSITIVE_PREFIXES = (
    "/api/auth/telegram",
    "/api/admin/",
    "/api/sync",
    "/sync",
    "/api/webhooks/",
)


def wants_json_response(request: Request) -> bool:
    """Return True when an error should be rendered as JSON, not as the reader shell."""
    path = request.url.path
    if path.startswith(API_PREFIXES):
        return True
    accept = (request.headers.get("accept") or "").lower()
    return "application/json" in accept and "text/html" not in accept


def client_ip_from_request(request: Request) -> str:
    """Return the best-effort client IP without trusting it as an identity."""
    forwarded_for = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded_for:
        return forwarded_for
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request id and lightweight timing data to every response.

    The request id is intentionally exposed in responses: it lets the admin match
    a user-facing error with Render logs without leaking secrets.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        request_id = (request.headers.get("x-request-id") or "").strip() or uuid.uuid4().hex
        request.state.request_id = request_id
        request.state.client_ip = client_ip_from_request(request)
        started_at = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-ms"] = f"{elapsed_ms:.2f}"
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add conservative browser safety headers that do not break Telegram WebView."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=()")
        # X-Frame-Options is intentionally not set: Telegram WebView may need to embed the app.
        return response


class ResponseCacheHeadersMiddleware(BaseHTTPMiddleware):
    """Keep HTML fresh while allowing short caching of static assets.

    CSS/JS are loaded through cache-busted URLs generated from file hashes,
    so static assets may be cached longer without keeping stale UI after deploy.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", f"public, max-age={max(0, settings.static_cache_seconds)}, immutable")
        elif path.startswith(API_PREFIXES):
            response.headers.setdefault("Cache-Control", "no-store")
        elif response.media_type == "text/html" or "text/html" in response.headers.get("content-type", ""):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


@dataclass(slots=True)
class _RateLimitBucket:
    hits: deque[float] = field(default_factory=deque)


class InMemoryRateLimiter:
    """Tiny per-process sliding-window limiter.

    It is intentionally simple: enough to protect public endpoints from obvious
    accidental loops and brute-force token checks on a single Render instance.
    It is not a substitute for a CDN/WAF if traffic grows.

    Relies on render.yaml running a single uvicorn worker (--workers 1) and a
    single service instance. With more workers/instances each process gets
    its own buckets, so the effective limit becomes limit * process_count.
    Move this to a shared store (Redis) before raising worker/instance count.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _RateLimitBucket] = {}
        self._last_cleanup = time.monotonic()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time.monotonic()
        window = max(1, int(window_seconds or 60))
        limit = max(1, int(limit or 1))
        bucket = self._buckets.setdefault(key, _RateLimitBucket())
        cutoff = now - window
        while bucket.hits and bucket.hits[0] <= cutoff:
            bucket.hits.popleft()
        if len(bucket.hits) >= limit:
            retry_after = max(1, int(window - (now - bucket.hits[0])))
            return False, 0, retry_after
        bucket.hits.append(now)
        remaining = max(0, limit - len(bucket.hits))
        if now - self._last_cleanup > window:
            self._cleanup(cutoff)
            self._last_cleanup = now
        return True, remaining, 0

    def _cleanup(self, cutoff: float) -> None:
        empty_keys: list[str] = []
        for key, bucket in self._buckets.items():
            while bucket.hits and bucket.hits[0] <= cutoff:
                bucket.hits.popleft()
            if not bucket.hits:
                empty_keys.append(key)
        for key in empty_keys:
            self._buckets.pop(key, None)


_rate_limiter = InMemoryRateLimiter()


def _rate_limit_scope(path: str) -> str:
    if path.startswith(SENSITIVE_PREFIXES):
        return "sensitive"
    if path.startswith("/static/"):
        return "static"
    return "public"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Add conservative in-memory rate limits to protect expensive endpoints."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)
        scope = _rate_limit_scope(request.url.path)
        if scope == "static":
            return await call_next(request)
        limit = settings.rate_limit_sensitive_max_requests if scope == "sensitive" else settings.rate_limit_public_max_requests
        client_ip = getattr(request.state, "client_ip", None) or client_ip_from_request(request)
        key = f"{scope}:{client_ip}"
        allowed, remaining, retry_after = _rate_limiter.allow(
            key,
            limit=limit,
            window_seconds=settings.rate_limit_window_seconds,
        )
        if not allowed:
            request_id = getattr(request.state, "request_id", "") or uuid.uuid4().hex
            headers = {
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-Request-ID": request_id,
            }
            if wants_json_response(request):
                return JSONResponse(
                    {
                        "ok": False,
                        "status_code": 429,
                        "error": "rate_limit_exceeded",
                        "request_id": request_id,
                    },
                    status_code=429,
                    headers=headers,
                )
            return Response("Too Many Requests", status_code=429, headers=headers)
        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(limit))
        response.headers.setdefault("X-RateLimit-Remaining", str(remaining))
        return response


def install_middlewares(app: FastAPI) -> None:
    # Order matters in Starlette: the last added middleware wraps earlier ones.
    # Request context must be outermost so error/rate-limit responses still have request ids.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ResponseCacheHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or "unknown"


def _safe_fox(get_fox: Callable[[], dict[str, Any] | None]) -> dict[str, Any] | None:
    try:
        return get_fox()
    except Exception:  # pragma: no cover - defensive fallback for broken DB/config
        logger.exception("Failed to load fox asset for error page")
        return None


def install_exception_handlers(
    app: FastAPI,
    *,
    templates: Jinja2Templates,
    app_title: str,
    get_fox: Callable[[], dict[str, Any] | None],
) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = _request_id(request)
        if wants_json_response(request):
            return JSONResponse(
                {
                    "ok": False,
                    "status_code": exc.status_code,
                    "error": exc.detail,
                    "request_id": request_id,
                },
                status_code=exc.status_code,
                headers={"X-Request-ID": request_id},
            )

        message = "Страница не найдена." if exc.status_code == 404 else str(exc.detail or "Ошибка.")
        return templates.TemplateResponse(
            request,
            "index.html",
            {"app_title": app_title, "error": message, "fox": _safe_fox(get_fox), "request_id": request_id},
            status_code=exc.status_code,
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = _request_id(request)
        logger.exception("Unhandled request error", extra={"request_id": request_id, "path": request.url.path})
        if wants_json_response(request):
            return JSONResponse(
                {
                    "ok": False,
                    "status_code": 500,
                    "error": "internal_server_error",
                    "request_id": request_id,
                },
                status_code=500,
                headers={"X-Request-ID": request_id},
            )

        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "app_title": app_title,
                "error": "Внутренняя ошибка приложения. Попробуйте обновить страницу.",
                "fox": _safe_fox(get_fox),
                "request_id": request_id,
            },
            status_code=500,
            headers={"X-Request-ID": request_id},
        )
