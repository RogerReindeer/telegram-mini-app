"""Shared API field names used by the web client and tests."""

USER_STATE_TABLE = "user_novel_state"
CHAPTER_PROGRESS_TABLE = "user_chapter_progress"

USER_STATE_ROUTES = (
    "/api/user/state",
    "/api/user/progress",
    "/api/user/progress/reset",
    "/api/user/library",
)

SYNC_ROUTES = ("/api/sync", "/sync")
