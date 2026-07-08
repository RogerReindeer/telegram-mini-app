"""Regression tests for the cross-novel full_book_access leak.

has_full_book_access gates paid chapter content, so app.services.auth's
_entitlement_fields() must never grant it based on a different novel's
entitlement, or on a lookup that covered every novel because no novel_id was
given. See app/services/auth.py for the full explanation.
"""

from __future__ import annotations

import app.services.auth as auth


def test_no_novel_id_never_grants_access(monkeypatch):
    monkeypatch.setattr(auth, "get_active_book_entitlements", lambda user_id, novel_id=None: ([], True))
    entitlements, full_book = auth._entitlement_fields(1, None, None)
    assert entitlements == []
    assert full_book is False


def test_owned_novel_grants_access(monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_active_book_entitlements",
        lambda user_id, novel_id=None: ([{"access_type": "full_book", "novel_id": novel_id}], True),
    )
    _entitlements, full_book = auth._entitlement_fields(1, 1, None)
    assert full_book is True


def test_transient_failure_does_not_leak_a_different_novels_stale_grant(monkeypatch):
    monkeypatch.setattr(auth, "get_active_book_entitlements", lambda user_id, novel_id=None: ([], False))
    stale_profile_for_other_novel = {
        "novel_id": 1,
        "book_entitlements": [{"access_type": "full_book"}],
        "has_full_book_access": True,
    }
    entitlements, full_book = auth._entitlement_fields(1, 999, stale_profile_for_other_novel)
    assert full_book is False
    assert entitlements == []


def test_transient_failure_preserves_same_novels_stale_grant(monkeypatch):
    monkeypatch.setattr(auth, "get_active_book_entitlements", lambda user_id, novel_id=None: ([], False))
    stale_profile_for_same_novel = {
        "novel_id": 999,
        "book_entitlements": [{"access_type": "full_book"}],
        "has_full_book_access": True,
    }
    entitlements, full_book = auth._entitlement_fields(1, 999, stale_profile_for_same_novel)
    assert full_book is True
    assert entitlements == [{"access_type": "full_book"}]
