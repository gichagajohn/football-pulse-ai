"""
agents/content_decision_agent.py — Football Pulse AI
Scores events for importance, checks for duplicates, decides what to post.
"""

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import settings
from database.schema import get_connection
from utils.logger import setup_logger

logger = setup_logger("decision_agent")


# ─────────────────────────────────────────────────────────────────────────────
# Priority scoring
# ─────────────────────────────────────────────────────────────────────────────

EVENT_BASE_SCORE = {
    "GOAL":             30,
    "FULLTIME":         25,
    "MATCHDAY":         20,
    "STARTING_XI":      15,
    "LEAGUE_TABLE":     15,
    "TOP_SCORERS":      15,
    "TOP_ASSISTS":      15,
    "TRANSFER_ALERT":   20,
    "INJURY_UPDATE":    15,
    "FOOTBALL_FACT":    10,
    "WORLD_CUP_FACT":   20,
    "RECORD_BROKEN":    25,
    "ON_THIS_DAY":      12,
    "TODAYS_FIXTURES":  18,
    "HALF_TIME":        15,
}


def score_event(event_type: str, competition: str, extra: dict = None) -> int:
    """
    Returns a priority score 0-100.
    Higher = more important = more likely to be published.
    """
    base = EVENT_BASE_SCORE.get(event_type, 10)
    comp_score = settings.COMPETITION_PRIORITY.get(
        competition,
        settings.COMPETITION_PRIORITY["default"]
    )
    # Weighted blend: 40% event type base + 60% competition importance
    score = int(base * 0.4 + comp_score * 0.6)

    # Bonus modifiers
    if extra:
        # Big wins / comebacks / late goals boost virality
        if extra.get("is_late_goal"):        score = min(score + 10, 100)
        if extra.get("is_comeback"):         score = min(score + 8, 100)
        if extra.get("is_penalty"):          score = min(score + 5, 100)
        if extra.get("is_record"):           score = min(score + 15, 100)
        if extra.get("is_big_team_match"):   score = min(score + 8, 100)
        if extra.get("is_derby"):            score = min(score + 12, 100)

    return score


def should_post(event_type: str, competition: str, extra: dict = None) -> tuple[bool, int]:
    """Return (post_it, priority_score)."""
    priority = score_event(event_type, competition, extra)
    post_it  = priority >= settings.MIN_PRIORITY_TO_POST
    return post_it, priority


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate detection
# ─────────────────────────────────────────────────────────────────────────────

def _make_event_key(match_id: str, event_type: str, minute: int = None, player: str = None) -> str:
    parts = [str(match_id), event_type]
    if minute is not None:
        parts.append(str(minute))
    if player:
        parts.append(player.lower().replace(" ", "_"))
    return ":".join(parts)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def is_duplicate(
    match_id: str,
    event_type: str,
    minute: int = None,
    player: str = None,
    caption: str = None,
) -> bool:
    """True if this event has already been posted within DEDUPE_WINDOW_HOURS."""
    key = _make_event_key(match_id, event_type, minute, player)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.DEDUPE_WINDOW_HOURS)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM post_history WHERE event_key=? AND posted_at > ?",
            (key, cutoff.isoformat())
        ).fetchone()

    if row:
        logger.debug("Duplicate detected for key: %s", key)
        return True
    return False


def record_post(
    match_id: str,
    event_type: str,
    minute: int = None,
    player: str = None,
    caption: str = None,
    poster_path: str = None,
):
    """Mark this event as posted so it won't be published again."""
    key          = _make_event_key(match_id, event_type, minute, player)
    caption_hash = _text_hash(caption) if caption else None
    poster_hash  = _text_hash(poster_path) if poster_path else None

    with get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO post_history(event_key, caption_hash, poster_hash)
               VALUES(?,?,?)""",
            (key, caption_hash, poster_hash)
        )
    logger.debug("Recorded post: %s", key)


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiting (MAX_POSTS_PER_HOUR)
# ─────────────────────────────────────────────────────────────────────────────

def within_rate_limit() -> bool:
    """True if we haven't exceeded MAX_POSTS_PER_HOUR in the last 60 min."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM posts WHERE status='published' AND published_at > ?",
            (cutoff.isoformat(),)
        ).fetchone()
    count = row["cnt"] if row else 0
    ok = count < settings.MAX_POSTS_PER_HOUR
    if not ok:
        logger.warning("Rate limit reached: %d posts in last hour (max %d)", count, settings.MAX_POSTS_PER_HOUR)
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Store event in DB
# ─────────────────────────────────────────────────────────────────────────────

def store_event(
    event_id: str,
    event_type: str,
    competition: str = None,
    home_team: str = None,
    away_team: str = None,
    home_score: int = 0,
    away_score: int = 0,
    minute: int = None,
    player_name: str = None,
    assist_name: str = None,
    match_id: str = None,
    raw_data: dict = None,
    priority: int = 0,
) -> Optional[int]:
    """Insert event into DB; returns rowid or None if duplicate."""
    try:
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO events
                   (event_id, event_type, competition, home_team, away_team,
                    home_score, away_score, minute, player_name, assist_name,
                    match_id, raw_data, priority)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id, event_type, competition, home_team, away_team,
                    home_score, away_score, minute, player_name, assist_name,
                    match_id, json.dumps(raw_data) if raw_data else None, priority
                )
            )
            return cur.lastrowid if cur.lastrowid else None
    except Exception as e:
        logger.error("store_event error: %s", e)
        return None
