"""ASGI entrypoint.

The public import path is deliberately small and stable: ``app.main:app``.
The existing production behavior is preserved in ``application.py`` while
subsequent refactors can move services and routers out without changing Render.
"""

from .application import app

__all__ = ["app"]
