"""Persistent product analytics for the Mini App.

The module stores compact, privacy-conscious events in Supabase and exposes
aggregates for the owner dashboard plus personal reading statistics. Analytics
must never break reading: every write is best-effort and failures are returned
as status data instead of bubbling into user-facing routes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from ..database import SupabaseError, db_insert, db_select
from ..utils import clean_value, to_float, to_int, utc_now


ALLOWED_EVENTS = {
    "app_open",
    "app_close",
    "main_group_gate_view",
    "main_group_join_click",
    "library_view",
    "library_search",
    "library_filter",
    "novel_impression",
    "novel_open",
    "toc_open",
    "start_reading_click",
    "continue_reading_click",
    "chapter_open",
    "chapter_progress",
    "chapter_complete",
    "chapter_close",
    "chapter_next",
    "chapter_previous",
    "access_denied",
    "paywall_view",
    "subscription_click",
    "favorite_add",
    "favorite_remove",
    "reading_add",
    "reading_remove",
    "completed_add",
    "completed_remove",
    "settings_open",
    "setting_change",
    "stats_view",
    "error",
}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: Any) -> datetime | None:
    text = clean_value(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _safe_text(value: Any, limit: int) -> str:
    return clean_value(value)[:limit]


def _sanitize_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, item in list(value.items())[:24]:
        safe_key = _safe_text(key, 80)
        if not safe_key:
            continue
        if isinstance(item, bool) or item is None:
            result[safe_key] = item
        elif isinstance(item, (int, float)):
            result[safe_key] = item
        elif isinstance(item, str):
            result[safe_key] = item[:300]
        elif isinstance(item, (list, tuple)):
            result[safe_key] = [str(part)[:120] for part in list(item)[:12]]
        elif isinstance(item, dict):
            nested: dict[str, Any] = {}
            for nested_key, nested_value in list(item.items())[:10]:
                if isinstance(nested_value, (str, int, float, bool)) or nested_value is None:
                    nested[str(nested_key)[:60]] = nested_value if not isinstance(nested_value, str) else nested_value[:160]
            result[safe_key] = nested
    # Keep event rows deliberately small even if a caller accidentally sends a lot.
    while result and len(json.dumps(result, ensure_ascii=False)) > 4096:
        result.pop(next(reversed(result)))
    return result


def record_analytics_event(telegram_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist one analytics event without exposing database failures to readers."""
    user_id = to_int(telegram_user_id, 0)
    event_name = _safe_text(payload.get("event_name"), 80)
    event_id = _safe_text(payload.get("event_id"), 100)
    if user_id <= 0:
        return {"status": "ignored", "reason": "missing_user"}
    if event_name not in ALLOWED_EVENTS:
        return {"status": "ignored", "reason": "unsupported_event"}
    if not event_id:
        return {"status": "ignored", "reason": "missing_event_id"}

    row = {
        "event_id": event_id,
        "telegram_user_id": user_id,
        "session_id": _safe_text(payload.get("session_id"), 100),
        "event_name": event_name,
        "novel_id": to_int(payload.get("novel_id"), 0) or None,
        "chapter_id": _safe_text(payload.get("chapter_id"), 80) or None,
        "source": _safe_text(payload.get("source"), 120) or "direct",
        "section": _safe_text(payload.get("section"), 80) or None,
        "action": _safe_text(payload.get("action"), 80) or None,
        "access_type": _safe_text(payload.get("access_type"), 80) or None,
        "subscription_type": _safe_text(payload.get("subscription_type"), 80) or None,
        "value_int": to_int(payload.get("value_int"), 0) if payload.get("value_int") is not None else None,
        "value_float": to_float(payload.get("value_float"), 0.0) if payload.get("value_float") is not None else None,
        "value_text": _safe_text(payload.get("value_text"), 300) or None,
        "metadata": _sanitize_metadata(payload.get("metadata")),
    }
    try:
        db_insert("analytics_events", row, prefer="return=minimal")
        return {"status": "ok", "stored": True, "event_id": event_id}
    except SupabaseError as error:
        text = str(error)
        if "23505" in text or "duplicate key" in text.lower():
            return {"status": "ok", "stored": False, "duplicate": True, "event_id": event_id}
        # Missing migration must not take the reader down.
        return {"status": "degraded", "stored": False, "detail": text[:240]}
    except Exception as error:  # pragma: no cover - defensive runtime guard
        return {"status": "degraded", "stored": False, "detail": str(error)[:240]}


def personal_reading_stats(telegram_user_id: int) -> dict[str, Any]:
    """Return user-facing reading counters from durable progress tables."""
    user_id = to_int(telegram_user_id, 0)
    if user_id <= 0:
        return {
            "chapters_opened": 0,
            "chapters_read": 0,
            "chapters_finished": 0,
            "novels_started": 0,
            "novels_completed": 0,
            "currently_reading": 0,
            "last_read_at": "",
        }

    progress_rows = db_select(
        "user_chapter_progress",
        select="novel_id,chapter_id,progress_percent,completed,last_read_at",
        filters={"telegram_user_id": f"eq.{user_id}"},
        order="last_read_at.desc",
    )
    state_rows = db_select(
        "user_novel_state",
        select="novel_id,is_reading,is_finished,last_read_at,updated_at",
        filters={"telegram_user_id": f"eq.{user_id}"},
        order="updated_at.desc",
    )

    opened_chapter_ids = {
        clean_value(row.get("chapter_id"))
        for row in progress_rows
        if clean_value(row.get("chapter_id"))
    }
    read_chapter_ids = {
        clean_value(row.get("chapter_id"))
        for row in progress_rows
        if clean_value(row.get("chapter_id"))
        and (bool(row.get("completed")) or to_float(row.get("progress_percent"), 0.0) >= 0.9)
    }
    progress_novel_ids = {
        to_int(row.get("novel_id"), 0)
        for row in progress_rows
        if to_int(row.get("novel_id"), 0) > 0
    }
    state_novel_ids = {
        to_int(row.get("novel_id"), 0)
        for row in state_rows
        if to_int(row.get("novel_id"), 0) > 0 and (row.get("is_reading") or row.get("is_finished"))
    }
    completed_novel_ids = {
        to_int(row.get("novel_id"), 0)
        for row in state_rows
        if to_int(row.get("novel_id"), 0) > 0 and bool(row.get("is_finished"))
    }
    currently_reading_ids = {
        to_int(row.get("novel_id"), 0)
        for row in state_rows
        if to_int(row.get("novel_id"), 0) > 0 and bool(row.get("is_reading")) and not bool(row.get("is_finished"))
    }

    last_read_at = ""
    candidates = [
        clean_value(row.get("last_read_at")) or clean_value(row.get("updated_at"))
        for row in [*progress_rows, *state_rows]
    ]
    parsed = [(value, _parse_dt(value)) for value in candidates if value]
    parsed = [item for item in parsed if item[1] is not None]
    if parsed:
        last_read_at = max(parsed, key=lambda item: item[1])[0]

    return {
        "chapters_opened": len(opened_chapter_ids),
        "chapters_read": len(read_chapter_ids),
        # Backward-compatible alias for clients from v226-v236.
        "chapters_finished": len(read_chapter_ids),
        "novels_started": len(progress_novel_ids | state_novel_ids),
        "novels_completed": len(completed_novel_ids),
        "currently_reading": len(currently_reading_ids),
        "last_read_at": last_read_at,
    }


def _event_users(events: list[dict[str, Any]], start: datetime) -> set[int]:
    result: set[int] = set()
    for row in events:
        created = _parse_dt(row.get("created_at"))
        user_id = to_int(row.get("telegram_user_id"), 0)
        if created and created >= start and user_id > 0:
            result.add(user_id)
    return result


def _retention_rate(profiles: list[dict[str, Any]], active_dates: dict[int, set[str]], days_after: int, now: datetime) -> dict[str, Any]:
    eligible = 0
    returned = 0
    for profile in profiles:
        user_id = to_int(profile.get("telegram_user_id"), 0)
        first_seen = _parse_dt(profile.get("first_seen_at"))
        if user_id <= 0 or not first_seen:
            continue
        target_day = (first_seen + timedelta(days=days_after)).date()
        if target_day > now.date():
            continue
        eligible += 1
        if target_day.isoformat() in active_dates.get(user_id, set()):
            returned += 1
    rate = round((returned / eligible * 100), 1) if eligible else 0.0
    return {"eligible": eligible, "returned": returned, "rate": rate}


def build_analytics_summary(days: int = 30) -> dict[str, Any]:
    """Build owner-facing product analytics from persistent event rows."""
    period_days = max(1, min(to_int(days, 30), 90))
    now = utc_now()
    period_start = now - timedelta(days=period_days)
    lookback_start = now - timedelta(days=90)
    try:
        events = db_select(
            "analytics_events",
            filters={"created_at": f"gte.{_iso(lookback_start)}"},
            order="created_at.asc",
        )
        profiles = db_select(
            "analytics_user_profiles",
            select="telegram_user_id,first_seen_at,last_seen_at,first_source,current_source,total_events",
            order="last_seen_at.desc",
        )
    except Exception as error:
        return {
            "status": "migration_required",
            "detail": str(error)[:320],
            "period_days": period_days,
            "overview": {},
            "retention": {},
            "events": [],
            "sources": [],
            "novels": [],
        }

    try:
        progress_rows = db_select(
            "user_chapter_progress",
            select="telegram_user_id,novel_id,chapter_id,last_read_at",
            order="last_read_at.desc",
        )
    except Exception:
        progress_rows = []
    try:
        subscription_rows = db_select(
            "user_subscriptions",
            select="*",
            order="started_at.desc",
        )
    except Exception:
        subscription_rows = []

    period_events = [row for row in events if (_parse_dt(row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= period_start]
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    event_counts = Counter(clean_value(row.get("event_name")) or "unknown" for row in period_events)
    users_period = _event_users(events, period_start)
    sessions = {
        clean_value(row.get("session_id"))
        for row in period_events
        if clean_value(row.get("session_id"))
    }
    session_times: dict[str, list[datetime]] = defaultdict(list)
    for row in period_events:
        session_id = clean_value(row.get("session_id"))
        created = _parse_dt(row.get("created_at"))
        if session_id and created:
            session_times[session_id].append(created)
    session_durations = [
        max(times).timestamp() - min(times).timestamp()
        for times in session_times.values()
        if len(times) >= 2
    ]
    average_session_minutes = round(sum(session_durations) / len(session_durations) / 60, 1) if session_durations else 0.0

    daily_buckets: dict[str, dict[str, Any]] = {}
    for row in period_events:
        created = _parse_dt(row.get("created_at"))
        if not created:
            continue
        day = created.date().isoformat()
        bucket = daily_buckets.setdefault(day, {"date": day, "events": 0, "users": set(), "sessions": set(), "chapter_opens": 0, "chapters_completed": 0})
        bucket["events"] += 1
        user_id = to_int(row.get("telegram_user_id"), 0)
        if user_id > 0:
            bucket["users"].add(user_id)
        session_id = clean_value(row.get("session_id"))
        if session_id:
            bucket["sessions"].add(session_id)
        if clean_value(row.get("event_name")) == "chapter_open":
            bucket["chapter_opens"] += 1
        if clean_value(row.get("event_name")) == "chapter_complete":
            bucket["chapters_completed"] += 1
    daily_rows = []
    for day in sorted(daily_buckets):
        bucket = daily_buckets[day]
        daily_rows.append({
            "date": day,
            "events": bucket["events"],
            "active_users": len(bucket["users"]),
            "sessions": len(bucket["sessions"]),
            "chapter_opens": bucket["chapter_opens"],
            "chapters_completed": bucket["chapters_completed"],
        })

    active_dates: dict[int, set[str]] = defaultdict(set)
    for row in events:
        user_id = to_int(row.get("telegram_user_id"), 0)
        created = _parse_dt(row.get("created_at"))
        if user_id > 0 and created:
            active_dates[user_id].add(created.date().isoformat())

    source_users: dict[str, set[int]] = defaultdict(set)
    source_events: Counter[str] = Counter()
    for row in period_events:
        source = clean_value(row.get("source")) or "direct"
        source_events[source] += 1
        user_id = to_int(row.get("telegram_user_id"), 0)
        if user_id > 0:
            source_users[source].add(user_id)

    source_rows = [
        {"source": source, "users": len(source_users[source]), "events": count}
        for source, count in source_events.most_common()
    ]

    novel_stats: dict[int, dict[str, Any]] = {}
    tracked_names = {"novel_impression", "novel_open", "toc_open", "chapter_open", "chapter_complete", "paywall_view", "subscription_click"}
    for row in period_events:
        novel_id = to_int(row.get("novel_id"), 0)
        event_name = clean_value(row.get("event_name"))
        if novel_id <= 0 or event_name not in tracked_names:
            continue
        item = novel_stats.setdefault(novel_id, {"novel_id": novel_id, "users": set(), **{name: 0 for name in tracked_names}})
        item[event_name] += 1
        user_id = to_int(row.get("telegram_user_id"), 0)
        if user_id > 0:
            item["users"].add(user_id)

    novel_titles: dict[int, str] = {}
    try:
        for novel in db_select("novels", select="novel_id,novel_short,title_ru,code"):
            novel_id = to_int(novel.get("novel_id"), 0)
            if novel_id > 0:
                novel_titles[novel_id] = clean_value(novel.get("novel_short")) or clean_value(novel.get("title_ru")) or clean_value(novel.get("code")) or str(novel_id)
    except Exception:
        pass

    novel_rows: list[dict[str, Any]] = []
    for novel_id, item in novel_stats.items():
        opens = int(item.get("novel_open") or item.get("toc_open") or 0)
        chapter_opens = int(item.get("chapter_open") or 0)
        novel_rows.append({
            "novel_id": novel_id,
            "title": novel_titles.get(novel_id, str(novel_id)),
            "users": len(item.pop("users")),
            **item,
            "start_rate": round(chapter_opens / opens * 100, 1) if opens else 0.0,
        })
    novel_rows.sort(key=lambda item: (item.get("chapter_open", 0), item.get("toc_open", 0)), reverse=True)

    new_users = 0
    for profile in profiles:
        first_seen = _parse_dt(profile.get("first_seen_at"))
        if first_seen and first_seen >= period_start:
            new_users += 1

    all_time_chapter_pairs = {
        (to_int(row.get("telegram_user_id"), 0), clean_value(row.get("chapter_id")))
        for row in progress_rows
        if to_int(row.get("telegram_user_id"), 0) > 0 and clean_value(row.get("chapter_id"))
    }
    all_time_reader_users = {user_id for user_id, _chapter_id in all_time_chapter_pairs}
    subscriptions_started = [
        row for row in subscription_rows
        if (_parse_dt(row.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= period_start
    ]
    subscription_users = {
        to_int(row.get("telegram_user_id"), 0)
        for row in subscriptions_started
        if to_int(row.get("telegram_user_id"), 0) > 0
    }

    reader_counts: dict[int, set[str]] = defaultdict(set)
    reader_novels: dict[int, set[int]] = defaultdict(set)
    reader_last: dict[int, datetime] = {}
    for row in progress_rows:
        user_id = to_int(row.get("telegram_user_id"), 0)
        chapter_id = clean_value(row.get("chapter_id"))
        novel_id = to_int(row.get("novel_id"), 0)
        when = _parse_dt(row.get("last_read_at"))
        if user_id <= 0 or not chapter_id:
            continue
        reader_counts[user_id].add(chapter_id)
        if novel_id > 0:
            reader_novels[user_id].add(novel_id)
        if when and (user_id not in reader_last or when > reader_last[user_id]):
            reader_last[user_id] = when
    reader_rows = [
        {
            "user_id": user_id,
            "chapters_read": len(chapters),
            "novels_started": len(reader_novels.get(user_id, set())),
            "last_read_at": _iso(reader_last[user_id]) if user_id in reader_last else "",
        }
        for user_id, chapters in reader_counts.items()
    ]
    reader_rows.sort(key=lambda row: (row["chapters_read"], row["last_read_at"]), reverse=True)

    overview = {
        "active_users": len(users_period),
        "new_users": new_users,
        "dau": len(_event_users(events, today_start)),
        "wau": len(_event_users(events, week_start)),
        "mau": len(_event_users(events, month_start)),
        "sessions": len(sessions),
        "avg_session_minutes": average_session_minutes,
        "events": len(period_events),
        "chapter_opens": event_counts.get("chapter_open", 0),
        "chapters_completed": event_counts.get("chapter_complete", 0),
        "paywalls": event_counts.get("paywall_view", 0),
        "subscription_clicks": event_counts.get("subscription_click", 0),
        "subscriptions_started": len(subscription_users),
        "chapters_read_all_time": len(all_time_chapter_pairs),
        "readers_all_time": len(all_time_reader_users),
        "avg_chapters_per_reader": round(len(all_time_chapter_pairs) / len(all_time_reader_users), 1) if all_time_reader_users else 0.0,
    }

    return {
        "status": "ok",
        "period_days": period_days,
        "generated_at": _iso(now),
        "overview": overview,
        "retention": {
            "d1": _retention_rate(profiles, active_dates, 1, now),
            "d7": _retention_rate(profiles, active_dates, 7, now),
            "d30": _retention_rate(profiles, active_dates, 30, now),
        },
        "events": [{"event_name": name, "count": count} for name, count in event_counts.most_common()],
        "sources": source_rows,
        "novels": novel_rows[:30],
        "readers": reader_rows[:50],
        "daily": daily_rows,
    }
