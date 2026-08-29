from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response

from ..config import settings
from ..services.media import ExternalImageError, fetch_external_image


router = APIRouter()


@router.get("/media/image", include_in_schema=False)
def external_image(url: str = Query(..., min_length=8, max_length=4096)):
    try:
        payload = fetch_external_image(url)
    except ExternalImageError:
        return Response(status_code=404, headers={"Cache-Control": "public, max-age=60"})

    return Response(
        content=payload["body"],
        media_type=payload["content_type"],
        headers={
            "Cache-Control": f"public, max-age={max(60, settings.image_cache_seconds)}",
            "X-Content-Type-Options": "nosniff",
        },
    )
