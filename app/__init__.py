"""ASGI compatibility exports.

Primary Render command remains:
    uvicorn app.main:app --host 0.0.0.0 --port $PORT

This export also keeps the app bootable if Render dashboard still has
an older command:
    uvicorn app:app --host 0.0.0.0 --port $PORT
"""
from .main import app

__all__ = ["app"]
