"""Server-to-server authentication for Qinghe -> Reader financial events."""

from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from collections import OrderedDict
from typing import Any

from fastapi import HTTPException, Request

from ..config import settings

INTERNAL_COMMERCE_BODY_LIMIT_BYTES = 16 * 1024
_NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")
_nonce_lock = threading.Lock()
_seen_nonces: OrderedDict[str, float] = OrderedDict()


def _signature_for(*, timestamp: str, nonce: str, body: bytes, secret: str) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    signing_string = f"{timestamp}.{nonce}.{body_hash}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), signing_string, hashlib.sha256).hexdigest()


def _remember_nonce(nonce: str, now: float) -> bool:
    """Best-effort replay guard; financial idempotency remains enforced in PostgreSQL."""
    ttl = max(60, int(settings.reader_commerce_nonce_ttl_seconds or 600))
    cutoff = now - ttl
    with _nonce_lock:
        while _seen_nonces:
            first_nonce, seen_at = next(iter(_seen_nonces.items()))
            if seen_at > cutoff:
                break
            _seen_nonces.pop(first_nonce, None)
        if nonce in _seen_nonces:
            return False
        _seen_nonces[nonce] = now
        while len(_seen_nonces) > 10_000:
            _seen_nonces.popitem(last=False)
        return True


def require_qinghe_signature(request: Request, raw_body: bytes) -> dict[str, Any]:
    if not settings.reader_coin_grants_enabled:
        raise HTTPException(status_code=503, detail="reader_coin_grants_disabled")
    if not settings.qinghe_commerce_shared_secret:
        raise HTTPException(status_code=503, detail="QINGHE_COMMERCE_SHARED_SECRET не настроен")

    service_id = (request.headers.get("x-service-id") or "").strip()
    timestamp = (request.headers.get("x-timestamp") or "").strip()
    nonce = (request.headers.get("x-nonce") or "").strip()
    signature = (request.headers.get("x-signature") or "").strip().lower()

    if service_id != settings.qinghe_commerce_service_id:
        raise HTTPException(status_code=401, detail="invalid_service")
    if not timestamp or not nonce or not signature:
        raise HTTPException(status_code=401, detail="missing_signature_headers")
    if not _NONCE_RE.fullmatch(nonce):
        raise HTTPException(status_code=401, detail="invalid_nonce")

    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid_timestamp") from exc

    now = int(time.time())
    skew = max(30, int(settings.reader_commerce_clock_skew_seconds or 300))
    if abs(now - timestamp_value) > skew:
        raise HTTPException(status_code=401, detail="stale_signature")

    expected = _signature_for(
        timestamp=timestamp,
        nonce=nonce,
        body=raw_body,
        secret=settings.qinghe_commerce_shared_secret,
    )
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="invalid_signature")
    if not _remember_nonce(nonce, float(now)):
        raise HTTPException(status_code=401, detail="replayed_nonce")

    return {"service_id": service_id, "timestamp": timestamp_value, "nonce": nonce}


def make_qinghe_signature(*, timestamp: str, nonce: str, body: bytes, secret: str) -> str:
    """Public test/helper contract for the paired Qinghe implementation."""
    return _signature_for(timestamp=timestamp, nonce=nonce, body=body, secret=secret)
