from __future__ import annotations
from fastapi import APIRouter, Request, Query
from ..security import require_sync_token, read_limited_json
from ..services.sync import validate_payload, run_sync
router = APIRouter()
@router.post('/api/sync/validate')
@router.post('/sync/validate')
async def sync_validate(request: Request, token: str | None = Query(default=None)):
    require_sync_token(token)
    return validate_payload(await read_limited_json(request))
@router.post('/api/sync')
@router.post('/sync')
async def sync_write(request: Request, token: str | None = Query(default=None)):
    require_sync_token(token)
    return run_sync(await read_limited_json(request))
