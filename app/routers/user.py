from __future__ import annotations
from fastapi import APIRouter
from ..schemas import UserProgressRequest
from ..services.user_state import save_progress, get_history
router = APIRouter(prefix='/api/user')
@router.post('/progress')
def progress(payload: UserProgressRequest): return save_progress(payload.model_dump())
@router.get('/history')
def history(telegram_user_id: str | None = None): return get_history(telegram_user_id)
