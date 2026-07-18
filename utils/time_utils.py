"""
utils/time_utils.py — Football Pulse AI
Timezone-aware time helpers used across all agents.
"""

from datetime import datetime, timezone, timedelta
import pytz
import settings

_TZ = pytz.timezone(settings.TIMEZONE)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_local() -> datetime:
    return datetime.now(_TZ)


def utc_to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_TZ)


def format_kickoff(utc_str: str) -> str:
    """
    Convert ISO 8601 UTC string to local HH:MM.
    e.g. "2024-04-01T15:00:00Z" → "18:00" (for EAT)
    """
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        return utc_to_local(dt).strftime("%H:%M")
    except Exception:
        return "TBC"


def today_str() -> str:
    return now_local().strftime("%Y-%m-%d")


def is_weekend() -> bool:
    return now_local().weekday() >= 5  # Saturday=5, Sunday=6


def hours_until(hour: int) -> float:
    """Hours until the next occurrence of a given hour (local time)."""
    now  = now_local()
    next_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if next_time <= now:
        next_time += timedelta(days=1)
    return (next_time - now).total_seconds() / 3600
