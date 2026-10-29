from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.routers import user as user_router
from app.schemas import SaveProgressPayload
from app.services.user_state import ChapterNotFoundError


def make_request(path: str) -> Request:
    return Request({
        "type": "http",
        "method": "PUT",
        "path": path,
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
    })


def test_missing_chapter_returns_404_instead_of_internal_error(monkeypatch):
    router = user_router.create_user_router(
        lambda _request: {"authenticated": True, "app_access": True, "user_id": 42},
        lambda viewer: viewer,
    )
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/user/progress")
    monkeypatch.setattr(
        user_router,
        "save_user_progress",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ChapterNotFoundError("Глава не найдена")),
    )

    with pytest.raises(HTTPException) as caught:
        endpoint(
            make_request("/api/user/progress"),
            SaveProgressPayload(novel_id=1, chapter_id="1-1", scroll_position=0.5),
        )

    assert caught.value.status_code == 404
    assert caught.value.detail == "Глава не найдена"
