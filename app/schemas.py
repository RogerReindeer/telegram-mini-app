"""API request schemas.

Keep the public JSON contract explicit at the HTTP boundary.  Services still
receive plain dictionaries so the internal code stays easy to test.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .utils import parse_chapter_id


class StrictInputModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    def to_service_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump(exclude_none=True)  # type: ignore[attr-defined]
        return self.dict(exclude_none=True)


class SaveProgressPayload(StrictInputModel):
    novel_id: int = Field(..., gt=0)
    chapter_id: str = Field(..., min_length=1, max_length=80)
    scroll_position: float = Field(0.0, ge=0.0, le=1.0)
    scroll_position_px: int = Field(0, ge=0, le=10_000_000)
    completed: bool = True

    @field_validator("chapter_id")
    @classmethod
    def chapter_id_is_safe(cls, value: str) -> str:
        # Разрешаем реальные ChapterID из CRM:
        #   2-50     обычная глава;
        #   2-52-1   глава 52, часть 1;
        #   2-52-2   глава 52, часть 2.
        # Другие символы не допускаем, чтобы ID нельзя было использовать как путь/SQL-фрагмент.
        if not parse_chapter_id(value):
            raise ValueError("chapter_id должен быть в формате NovelID-ChapterNo или NovelID-ChapterNo-PartNo")
        return value


class ResetProgressPayload(StrictInputModel):
    novel_id: int = Field(..., gt=0)


class SaveLibraryPayload(StrictInputModel):
    novel_id: int = Field(..., gt=0)
    is_favorite: bool = False
    is_completed: bool | None = None
    is_finished: bool | None = None
    is_hidden: bool = False


class AnalyticsEventPayload(StrictInputModel):
    event_id: str = Field(..., min_length=8, max_length=100)
    session_id: str = Field("", max_length=100)
    event_name: str = Field(..., min_length=1, max_length=80)
    novel_id: int | None = Field(None, gt=0)
    chapter_id: str | None = Field(None, max_length=80)
    source: str = Field("direct", max_length=120)
    section: str | None = Field(None, max_length=80)
    action: str | None = Field(None, max_length=80)
    access_type: str | None = Field(None, max_length=80)
    subscription_type: str | None = Field(None, max_length=80)
    value_int: int | None = None
    value_float: float | None = None
    value_text: str | None = Field(None, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)
