NOVELS_TABLE = "novels"
CHAPTERS_TABLE = "chapters"
FOX_TABLE = "fox"
SYNC_RUNS_TABLE = "sync_runs"
USER_NOVEL_STATE_TABLE = "user_novel_state"
USER_CHAPTER_PROGRESS_TABLE = "user_chapter_progress"

PUBLIC_ROUTES = ["/", "/library", "/novel/{slug}", "/chapter/{chapter_id}"]
SYSTEM_ROUTES = ["/health", "/ready", "/version"]
SYNC_ROUTES = ["/sync", "/api/sync", "/api/sync/validate"]
ADMIN_ROUTES = ["/admin", "/api/admin/production/check", "/api/admin/content/audit"]
