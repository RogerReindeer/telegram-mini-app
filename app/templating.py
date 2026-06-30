from __future__ import annotations

from typing import Any
from fastapi import Request
from fastapi.responses import HTMLResponse


def render_template(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render Jinja templates without Starlette TemplateResponse signature ambiguity.

    New Starlette versions changed/overloaded TemplateResponse arguments. Passing
    arguments in the wrong order can produce a Jinja cache key crash on Python 3.14:
    `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')`.
    Rendering through the environment keeps the contract explicit and stable.
    """
    templates = request.app.state.templates
    payload: dict[str, Any] = {"request": request}
    if context:
        payload.update(context)
    html = templates.env.get_template(name).render(payload)
    return HTMLResponse(html, status_code=status_code)
