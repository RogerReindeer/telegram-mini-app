from __future__ import annotations

from typing import Any
from fastapi import Request


def viewer_from_request(request: Request) -> dict[str, Any]:
    role = request.cookies.get("zbz_role") or request.query_params.get("role") or "guest"
    if role not in {"guest", "traveler", "keeper"}:
        role = "guest"
    labels = {"guest": "Гость", "traveler": "🌱 Странствующий читатель", "keeper": "📜 Хранитель свитков"}
    return {"telegram_user_id": request.query_params.get("user_id"), "role": role, "role_label": labels[role]}


def authenticate_telegram_viewer(init_data: str | None) -> dict[str, Any]:
    # Safe placeholder: production verifies Telegram initData hash with bot token.
    return {"telegram_user_id": None, "role": "guest", "role_label": "Гость", "authenticated": False}
