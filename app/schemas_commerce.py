"""Strict HTTP schemas for the Reader Coins integration boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class TestCoinGrantRequest(CommerceInputModel):
    amount: int = Field(..., ge=10, le=100000)
    client_action_id: UUID


class StorePurchaseRequest(CommerceInputModel):
    product_code: str = Field(..., min_length=1, max_length=120)
    client_action_id: UUID

    @field_validator("product_code")
    @classmethod
    def strip_product_code(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("product_code must not be empty")
        return text


class StoreProductAdminPayload(CommerceInputModel):
    product_type: Literal["chapter_unlock", "novel_unlock", "subscription", "subscription_upgrade"]
    title: str = Field(..., min_length=1, max_length=240)
    coin_price: int = Field(..., ge=1, le=1_000_000)
    novel_id: int | None = Field(default=None, gt=0)
    chapter_id: str | None = Field(default=None, max_length=160)
    subscription_role: Literal["traveler", "keeper"] | None = None
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    upgrade_from_role: Literal["traveler", "keeper"] | None = None
    is_active: bool = True
    sort_order: int = Field(default=0, ge=-1_000_000, le=1_000_000)

    @field_validator("title", "chapter_id", mode="before")
    @classmethod
    def strip_optional_text(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def validate_target(self):
        if self.product_type == "chapter_unlock":
            if not self.novel_id or not self.chapter_id:
                raise ValueError("Для главы нужны novel_id и chapter_id")
            if self.subscription_role or self.duration_days:
                raise ValueError("У покупки главы не бывает роли подписки")
        elif self.product_type == "novel_unlock":
            if not self.novel_id or self.chapter_id:
                raise ValueError("Для бандла нужен только novel_id")
            if self.subscription_role or self.duration_days:
                raise ValueError("У бандла не бывает роли подписки")
        else:
            if self.novel_id or self.chapter_id:
                raise ValueError("Подписка не привязывается к отдельной книге или главе")
            if not self.subscription_role or not self.duration_days:
                raise ValueError("Для подписки нужны роль и срок в днях")
        return self


class BulkNovelPricingPayload(CommerceInputModel):
    novel_ids: str = Field(..., min_length=1, max_length=1000)
    chapter_coin_price: int = Field(..., ge=1, le=1_000_000)
    bundle_coin_price: int = Field(..., ge=1, le=1_000_000)

    @field_validator("novel_ids")
    @classmethod
    def strip_novel_ids(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Укажите ID новелл")
        return text


class TestPurchaseRollbackRequest(CommerceInputModel):
    confirmation: Literal["ROLLBACK_TEST_PURCHASES"]
    telegram_user_id: int | None = Field(default=None, gt=0)
