"""Strict HTTP schemas for the Reader Coins integration boundary."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommerceInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoinGrantPayload(CommerceInputModel):
    schema_version: int = Field(1, ge=1, le=1)
    event_id: UUID
    purchase_id: UUID
    telegram_user_id: int = Field(..., gt=0)
    product_code: str = Field(..., min_length=1, max_length=120)
    amount: int = Field(..., gt=0)
    currency: str = Field(..., min_length=1, max_length=40)
    provider: str = Field(..., min_length=1, max_length=80)
    occurred_at: datetime

    @field_validator("product_code", "provider", "currency")
    @classmethod
    def strip_safe_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("value must not be empty")
        return text
