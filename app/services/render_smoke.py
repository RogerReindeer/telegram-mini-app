"""Render deployment smoke-test contract.

The real checks are run from an operator machine against the deployed Render URL.
This module keeps the list of required URLs in source control so docs, admin API,
and tests cannot silently diverge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SmokeTarget:
    name: str
    method: str
    path: str
    expected_status: int
    kind: str
    requires_token: bool = False
    critical: bool = True
    note: str = ""


PUBLIC_SMOKE_TARGETS: tuple[SmokeTarget, ...] = (
    SmokeTarget("health", "GET", "/health", 200, "json", note="Process is alive and middleware works."),
    SmokeTarget("ready", "GET", "/ready", 200, "json", note="Shows Supabase/env readiness; may be degraded before env is configured."),
    SmokeTarget("version", "GET", "/version", 200, "json", note="Shows deployed app version and asset fingerprints."),
    SmokeTarget("library_page", "GET", "/library", 200, "html", note="Main Mini App entry page renders."),
    SmokeTarget("library_api", "GET", "/api/library", 200, "json", note="Catalog API returns JSON for the frontend."),
)

ADMIN_SMOKE_TARGETS: tuple[SmokeTarget, ...] = (
    SmokeTarget("render_smoke_plan", "GET", "/api/admin/render/smoke-plan", 200, "json", True, note="This checklist is exposed by the deployed app."),
    SmokeTarget("release_check", "GET", "/api/admin/release/check", 200, "json", True, note="Final launch gate."),
    SmokeTarget("content_audit", "GET", "/api/admin/content/audit", 200, "json", True, note="Real Supabase content audit."),
    SmokeTarget("production_check", "GET", "/api/admin/production/check", 200, "json", True, note="Production readiness report."),
    SmokeTarget("sync_status", "GET", "/api/admin/sync/status", 200, "json", True, False, note="Recent sync_runs; can be empty on first deploy."),
    SmokeTarget("cache_status", "GET", "/api/admin/cache", 200, "json", True, False, note="Cache statistics and namespace visibility."),
    SmokeTarget("admin_page", "GET", "/admin", 200, "html", True, False, note="Owner-facing HTML diagnostics."),
)


def render_smoke_targets() -> list[SmokeTarget]:
    return [*PUBLIC_SMOKE_TARGETS, *ADMIN_SMOKE_TARGETS]


def render_smoke_plan(*, base_url: str = "") -> dict[str, Any]:
    normalized_base = (base_url or "https://<your-render-app>.onrender.com").rstrip("/")
    targets = []
    for target in render_smoke_targets():
        url = f"{normalized_base}{target.path}"
        if target.requires_token:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}token=<SYNC_TOKEN>"
        targets.append({**asdict(target), "url": url})
    return {
        "status": "ok",
        "kind": "render_smoke_plan",
        "base_url": normalized_base,
        "targets": targets,
        "counts": {
            "total": len(targets),
            "public": len(PUBLIC_SMOKE_TARGETS),
            "admin": len(ADMIN_SMOKE_TARGETS),
            "critical": sum(1 for target in targets if target["critical"]),
        },
        "rules": [
            "Run after every Render deploy.",
            "Use the same SYNC_TOKEN as Google Apps Script.",
            "Do not paste tokens into screenshots or public chats.",
            "A degraded /ready is acceptable only before production env vars are configured.",
        ],
    }
