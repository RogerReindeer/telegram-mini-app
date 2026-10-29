from __future__ import annotations

from app.database import SupabaseClient


def test_supabase_client_retries_only_safe_read_methods():
    client = SupabaseClient("https://example.supabase.co", "service-key")
    retry = client.session.get_adapter("https://").max_retries

    assert "GET" in retry.allowed_methods
    assert "POST" not in retry.allowed_methods
    assert {429, 500, 502, 503, 504}.issubset(set(retry.status_forcelist))
