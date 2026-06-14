"""
database/schema.py — Football Pulse AI
SQLite schema definitions and initialisation helper.
"""

import sqlite3
import logging
from pathlib import Path
from settings import DB_PATH

logger = logging.getLogger(__name__)

DDL = """
-- ─────────────────────────────────────────────
-- Posts table (matches what publisher_agent.py writes)
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER DEFAULT 0,
    poster_path     TEXT,
    caption_text    TEXT,
    hashtags        TEXT    DEFAULT '',
    platform        TEXT    DEFAULT 'facebook',
    status          TEXT    DEFAULT 'pending',
    content_hash    TEXT,
    content_type    TEXT,
    competition     TEXT,
    fb_post_id      TEXT,
    ig_post_id      TEXT,
    error_message   TEXT,
    likes           INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0,
    shares          INTEGER DEFAULT 0,
    posted_at       DATETIME DEFAULT (datetime('now')),
    published_at    DATETIME
);

-- ─────────────────────────────────────────────
-- Events log
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key   TEXT    NOT NULL UNIQUE,
    event_type  TEXT    NOT NULL,
    competition TEXT,
    match_id    TEXT,
    created_at  DATETIME DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────
-- Post history (for duplicate detection)
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS post_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT    NOT NULL,
    content_type TEXT,
    posted_at    DATETIME DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────
-- Live match state (persists across GitHub Actions runs)
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS match_state (
    match_id    TEXT    PRIMARY KEY,
    home_score  INTEGER NOT NULL DEFAULT 0,
    away_score  INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'NS',
    updated_at  DATETIME DEFAULT (datetime('now'))
);
"""


def get_connection() -> sqlite3.Connection:
    """Return a connection with DELETE journal mode (single .db file, git-friendly)."""
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create all tables if they don't already exist."""
    with get_connection() as conn:
        conn.executescript(DDL)
    logger.info("Database initialised at %s", DB_PATH)