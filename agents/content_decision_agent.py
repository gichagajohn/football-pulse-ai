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

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Priority weights
# ─────────────────────────────────────────────

EVENT_BASE_PRIORITY: dict[str, int] = {
    "GOAL":             80,
    "FULLTIME":         70,
    "HALFTIME":         50,
    "TRANSFER_ALERT":   20,
    "INJURY_ALERT":     20,
    "FIXTURE_POST":     30,
    "FOOTBALL_FACT":    40,
    "ON_THIS_DAY":      40,
    "LINEUP":           35,
    "VAR_DECISION":     45,
    "RED_CARD":         60,
}

COMPETITION_PRIORITY: dict[str, int] = {
    # Top competitions
    "UEFA Champions League":        90,
    "UEFA Europa League":           80,
    "UEFA Europa Conference League":70,
    "Premier League":               90,
    "La Liga":                      85,
    "Bundesliga":                   80,
    "Serie A":                      80,
    "Ligue 1":                      75,
    "FIFA World Cup":               95,
    "UEFA European Championship":   92,
    "Africa Cup of Nations":        85,
    "Copa Libertadores":            75,
    # Default — raised to 60 so RSS transfer/injury articles can clear MIN_PRIORITY_TO_POST
    "default":                      60,
}


def _competition_score(competition: Optional[str]) -> int:
    if not competition:
        return COMPETITION_PRIORITY["default"]
    for key, score in COMPETITION_PRIORITY.items():
        if key.lower() in competition.lower():
            return score
    return COMPETITION_PRIORITY["default"]


def score_event(event_type: str, competition: Optional[str] = None) -> int:
    """Return a 0-100 priority score for this event."""
    base = EVENT_BASE_PRIORITY.get(event_type, 20)
    comp = _competition_score(competition)
    score = int(base * 0.4 + comp * 0.6)
    logger.debug("score_event(%s, %s) → base=%d comp=%d score=%d",
                 event_type, competition, base, comp, score)
    return score


def _make_hash(content_type: str, key: str) -> str:
    return hashlib.sha256(f"{content_type}:{key}".encode()).hexdigest()


def is_duplicate(content_type: str, key: str) -> bool:
    """Return True if this content was already posted within DEDUPE_WINDOW_HOURS."""
    h = _make_hash(content_type, key)
    window = timedelta(hours=settings.DEDUPE_WINDOW_HOURS)
    cutoff = datetime.now(timezone.utc) - window
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM posts WHERE content_hash = ? AND posted_at >= ?",
            (h, cutoff.isoformat()),
        ).fetchone()
    return row is not None


def record_post(content_type: str, key: str, competition: Optional[str] = None,
                fb_post_id: Optional[str] = None) -> None:
    """Record a successful post so future duplicate checks work."""
    h = _make_hash(content_type, key)
    with get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO posts
               (content_hash, content_type, competition, fb_post_id)
               VALUES (?, ?, ?, ?)""",
            (h, content_type, competition, fb_post_id),
        )


def should_post(event_type: str, competition: Optional[str] = None,
                dedup_key: Optional[str] = None) -> bool:
    """
    Return True if this event scores above the threshold AND hasn't been posted recently.
    """
    score = score_event(event_type, competition)
    if score < settings.MIN_PRIORITY_TO_POST:
        logger.info("should_post → SKIP %s/%s score=%d < threshold=%d",
                    event_type, competition, score, settings.MIN_PRIORITY_TO_POST)
        return False

    if dedup_key and is_duplicate(event_type, dedup_key):
        logger.info("should_post → DUPLICATE %s key=%s", event_type, dedup_key)
        return False

    logger.info("should_post → POST %s/%s score=%d", event_type, competition, score)
    return True