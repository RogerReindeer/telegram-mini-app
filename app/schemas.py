"""API request schemas.

Keep the public JSON contract explicit at the HTTP boundary.  Services still
receive plain dictionaries so the internal code stays easy to test.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, validator


class StrictInputModel(BaseModel):
    class Config:
        extra = "ignore"

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

    @validator("chapter_id")
    def chapter_id_is_safe(cls, value: str) -> str:
        if not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError("chapter_id содержит недопустимые символы")
        return value


class ResetProgressPayload(StrictInputModel):
    novel_id: int = Field(..., gt=0)


class SaveLibraryPayload(StrictInputModel):
    novel_id: int = Field(..., gt=0)
    is_favorite: bool = False
    is_completed: bool | None = None
    is_finished: bool | None = None
    is_hidden: bool = False
