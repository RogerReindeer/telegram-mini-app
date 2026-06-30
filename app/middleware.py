from __future__ import annotations

import time, uuid
from collections import defaultdict, deque
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from .config import settings

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            if request.url.path.startswith('/api/'):
                return JSONResponse({"error": "internal_error", "request_id": request.state.request_id}, status_code=500)
            raise exc
        response.headers.setdefault("X-Request-ID", request.state.request_id)
        response.headers.setdefault("X-Process-Time", f"{time.perf_counter() - started:.4f}")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return response

class ResponseCacheHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        path = request.url.path
        if path.startswith('/static/'):
            response.headers.setdefault("Cache-Control", f"public, max-age={settings.static_cache_seconds}")
        elif path.startswith('/api/') or response.headers.get('content-type', '').startswith('text/html'):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):
    _buckets: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith('/static/'):
            return await call_next(request)
        now = time.time()
        window = settings.rate_limit_window_seconds
        max_requests = settings.rate_limit_max_requests
        client = request.client.host if request.client else 'unknown'
        key = f"{client}:{request.url.path}"
        bucket = self._buckets[key]
        while bucket and bucket[0] < now - window:
            bucket.popleft()
        if len(bucket) >= max_requests:
            return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)
        bucket.append(now)
        return await call_next(request)
