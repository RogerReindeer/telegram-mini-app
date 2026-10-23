from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from app import security
from app.middleware import SecurityHeadersMiddleware


def make_request(*, headers: dict[str, str] | None = None, query: bytes = b"") -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/sync",
        "query_string": query,
        "headers": raw_headers,
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
    })


def test_sync_token_accepts_header_and_bearer(monkeypatch):
    monkeypatch.setattr(security, "settings", SimpleNamespace(sync_token="secret"))
    security.require_sync_token(make_request(headers={"x-sync-token": "secret"}))
    security.require_sync_token(make_request(headers={"authorization": "Bearer secret"}))


def test_sync_token_rejects_query_string(monkeypatch):
    monkeypatch.setattr(security, "settings", SimpleNamespace(sync_token="secret"))
    with pytest.raises(HTTPException) as caught:
        security.require_sync_token(make_request(query=b"token=secret"))
    assert caught.value.status_code == 403


def test_security_headers_include_csp_and_production_hsts(monkeypatch):
    import app.middleware as middleware_module

    monkeypatch.setattr(middleware_module, "settings", SimpleNamespace(app_env="production"))
    middleware = SecurityHeadersMiddleware(app=lambda scope, receive, send: None)

    async def call_next(_request):
        return Response("ok")

    response = asyncio.run(middleware.dispatch(make_request(), call_next))
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"].startswith("max-age=31536000")
