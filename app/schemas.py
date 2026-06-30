from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any

class UserProgressRequest(BaseModel):
    telegram_user_id: str | int | None = None
    novel_id: str | int
    chapter_id: str
    progress_percent: int = Field(default=0, ge=0, le=100)
    scroll_y: int = Field(default=0, ge=0)

class LibraryActionRequest(BaseModel):
    telegram_user_id: str | int | None = None
    novel_id: str | int
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
