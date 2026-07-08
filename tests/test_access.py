"""Access-decision matrix for app/services/access.py.

This is the single place that decides whether a viewer may read a chapter or
see a novel, so a regression here is a direct revenue/paywall leak (as
happened once already with the cross-novel has_full_book_access bug). These
tests pin down the documented rules in _decide_chapter_access_raw's
docstring:

- Traveler only gains visibility of gift (post_icons contains a gift marker)
  novels; premium dates do not open chapters for Traveler.
- Keeper reads chapters once premium_release_date has passed.
- A full-book entitlement reads every translated chapter of that novel.
- Everyone may read chapters once free_release_date has passed.
- Hidden chapter rows fail closed for ordinary users.
"""

from __future__ import annotations

from app.services.access import (
    _decide_chapter_access_raw,
    can_view_novel_for_profile,
    normalize_required_role,
    novel_is_gift,
    viewer_can_access_required_role,
)

PAST = "2000-01-01"
FUTURE = "2999-01-01"


def make_chapter(**overrides):
    base = {
        "is_visible": True,
        "translation_date": PAST,
        "access_level": "guest",
        "free_release_date": PAST,
        "premium_release_date": PAST,
        "telegraph_free_url": "https://telegra.ph/free",
        "telegraph_premium_url": "https://telegra.ph/premium",
        "telegraph_url": "https://telegra.ph/legacy",
    }
    base.update(overrides)
    return base


def make_novel(**overrides):
    base = {"post_icons": "", "access_model": ""}
    base.update(overrides)
    return base


def make_profile(role="guest", has_full_book_access=False):
    return {"role": role, "has_full_book_access": has_full_book_access}


GIFT_NOVEL = make_novel(post_icons="🎁 популярное")


# ---------------------------------------------------------------------------
# Small helpers used throughout the access decision
# ---------------------------------------------------------------------------

def test_novel_is_gift_detects_emoji_marker():
    assert novel_is_gift(make_novel(post_icons="🎁"))
    assert not novel_is_gift(make_novel(post_icons="🔥 популярное"))


def test_novel_is_gift_accepts_legacy_access_model_fallback():
    assert novel_is_gift(make_novel(access_model="BoostyOnly"))
    assert novel_is_gift(make_novel(access_model="boosty only"))


def test_normalize_required_role_buckets():
    assert normalize_required_role("") == "guest"
    assert normalize_required_role("free") == "guest"
    assert normalize_required_role("subscriber") == "traveler"
    assert normalize_required_role("premium") == "keeper"
    assert normalize_required_role("странствующий") == "traveler"
    assert normalize_required_role("something unrecognized") == "keeper"


def test_viewer_can_access_required_role_uses_role_rank():
    assert viewer_can_access_required_role("keeper", "traveler")
    assert viewer_can_access_required_role("traveler", "traveler")
    assert not viewer_can_access_required_role("traveler", "keeper")
    assert not viewer_can_access_required_role("guest", "traveler")


def test_can_view_novel_for_profile_gift_novel_requires_traveler_or_keeper():
    guest = make_profile(role="guest")
    traveler = make_profile(role="traveler")
    assert not can_view_novel_for_profile(GIFT_NOVEL, guest)
    assert can_view_novel_for_profile(GIFT_NOVEL, traveler)


def test_can_view_novel_for_profile_non_gift_always_visible():
    novel = make_novel()
    assert can_view_novel_for_profile(novel, make_profile(role="guest"))


def test_can_view_novel_for_profile_full_book_access_bypasses_gift_gate():
    guest_with_entitlement = make_profile(role="guest", has_full_book_access=True)
    assert can_view_novel_for_profile(GIFT_NOVEL, guest_with_entitlement)


# ---------------------------------------------------------------------------
# _decide_chapter_access_raw: the core paywall decision
# ---------------------------------------------------------------------------

def test_hidden_chapter_denied_for_ordinary_viewer():
    chapter = make_chapter(is_visible=False)
    decision = _decide_chapter_access_raw(chapter, make_novel(), make_profile(role="guest"))
    assert decision.status == "hidden"
    assert not decision.allowed


def test_hidden_chapter_visible_to_keeper():
    chapter = make_chapter(is_visible=False)
    decision = _decide_chapter_access_raw(chapter, make_novel(), make_profile(role="keeper"))
    assert decision.status != "hidden"


def test_hidden_chapter_visible_with_full_book_access():
    chapter = make_chapter(is_visible=False)
    profile = make_profile(role="guest", has_full_book_access=True)
    decision = _decide_chapter_access_raw(chapter, make_novel(), profile)
    assert decision.status != "hidden"


def test_untranslated_chapter_always_denied():
    chapter = make_chapter(translation_date="")
    decision = _decide_chapter_access_raw(chapter, make_novel(), make_profile(role="keeper"))
    assert decision.status == "not_translated"
    assert not decision.allowed


def test_full_book_access_opens_translated_chapter_preferring_premium_url():
    chapter = make_chapter()
    profile = make_profile(role="guest", has_full_book_access=True)
    decision = _decide_chapter_access_raw(chapter, make_novel(), profile)
    assert decision.status == "full_book_entitlement"
    assert decision.allowed
    assert decision.url == "https://telegra.ph/premium"


def test_full_book_access_falls_back_to_public_url_when_no_premium_source():
    chapter = make_chapter(telegraph_premium_url="")
    profile = make_profile(role="guest", has_full_book_access=True)
    decision = _decide_chapter_access_raw(chapter, make_novel(), profile)
    assert decision.status == "full_book_entitlement"
    assert decision.url == "https://telegra.ph/free"


def test_full_book_access_without_any_source_falls_through_instead_of_granting():
    """A full_book_access grant never fabricates a URL: with no source at all
    the decision must still be a denial, not `allowed=True, url=""`."""
    chapter = make_chapter(telegraph_premium_url="", telegraph_free_url="", telegraph_url="")
    profile = make_profile(role="guest", has_full_book_access=True)
    decision = _decide_chapter_access_raw(chapter, make_novel(), profile)
    assert not decision.allowed
    assert not decision.url


def test_gift_novel_denies_guest_without_full_book_access():
    decision = _decide_chapter_access_raw(make_chapter(), GIFT_NOVEL, make_profile(role="guest"))
    assert decision.status == "book_access_denied"
    assert not decision.allowed
    assert decision.required_role == "traveler"


def test_gift_novel_open_chapter_readable_by_traveler():
    decision = _decide_chapter_access_raw(make_chapter(), GIFT_NOVEL, make_profile(role="traveler"))
    assert decision.status == "public_open"
    assert decision.allowed


def test_keeper_reads_premium_ready_chapter():
    chapter = make_chapter(premium_release_date=PAST, free_release_date=FUTURE)
    decision = _decide_chapter_access_raw(chapter, make_novel(), make_profile(role="keeper"))
    assert decision.status == "premium_open"
    assert decision.allowed
    assert decision.url == "https://telegra.ph/premium"


def test_traveler_does_not_get_early_premium_access():
    """Traveler only gains gift-novel visibility; a premium release date must
    not open the chapter for them ahead of the free release date."""
    chapter = make_chapter(premium_release_date=PAST, free_release_date=FUTURE)
    decision = _decide_chapter_access_raw(chapter, make_novel(), make_profile(role="traveler"))
    assert not decision.allowed
    assert decision.status != "premium_open"


def test_anyone_reads_after_free_release_date():
    chapter = make_chapter(free_release_date=PAST, premium_release_date=FUTURE)
    for role in ("guest", "traveler", "keeper"):
        decision = _decide_chapter_access_raw(chapter, make_novel(), make_profile(role=role))
        assert decision.status == "public_open", role
        assert decision.allowed, role


def test_keeper_sees_premium_scheduled_before_release():
    chapter = make_chapter(premium_release_date=FUTURE, free_release_date=FUTURE)
    decision = _decide_chapter_access_raw(chapter, make_novel(), make_profile(role="keeper"))
    assert decision.status == "premium_scheduled"
    assert not decision.allowed
    assert decision.release_date == FUTURE


def test_guest_sees_free_scheduled_before_release_when_source_exists():
    chapter = make_chapter(free_release_date=FUTURE, premium_release_date=FUTURE)
    decision = _decide_chapter_access_raw(chapter, make_novel(), make_profile(role="guest"))
    assert decision.status == "free_scheduled"
    assert not decision.allowed
    assert decision.release_date == FUTURE


def test_guest_sees_no_content_source_when_nothing_is_scheduled_or_linked():
    chapter = make_chapter(
        free_release_date=FUTURE,
        premium_release_date=FUTURE,
        telegraph_free_url="",
        telegraph_premium_url="",
        telegraph_url="",
    )
    decision = _decide_chapter_access_raw(chapter, make_novel(), make_profile(role="guest"))
    assert decision.status == "no_content_source"
    assert not decision.allowed
