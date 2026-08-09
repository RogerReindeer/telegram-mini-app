from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import AnalyticsEventPayload
from ..services.analytics import record_analytics_event
from ..services.auth import public_viewer, viewer_from_request


router = APIRouter(prefix="/api/analytics")


@router.post("/event")
def event(request: Request, payload: AnalyticsEventPayload):
    viewer = public_viewer(viewer_from_request(request))
    if not viewer.get("authenticated") or not viewer.get("user_id"):
        raise HTTPException(status_code=401, detail="Откройте приложение внутри Telegram")
    return record_analytics_event(int(viewer["user_id"]), payload.to_service_dict())
