from __future__ import annotations
from fastapi import APIRouter
from ..services.auth import authenticate_telegram_viewer
router = APIRouter(prefix='/api/auth')
@router.post('/telegram')
def telegram_auth(payload: dict): return authenticate_telegram_viewer(payload.get('init_data'))
@router.get('/profile')
def profile(): return {"role": "guest", "role_label": "Гость"}
