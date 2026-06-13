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
-- EVENTS: raw football events from APIs
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT UNIQUE NOT NULL,
    event_type      TEXT NOT NULL,          -- GOAL, FULLTIME, MATCHDAY, etc.
    competition     TEXT,
    home_team       TEXT,
    away_team       TEXT,
    home_score      INTEGER DEFAULT 0,
    away_score      INTEGER DEFAULT 0,
    minute          INTEGER,
    player_name     TEXT,
    assist_name     TEXT,
    match_id        TEXT,
    raw_data        TEXT,                   -- JSON blob of full API payload
    priority        INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- POSTS: every post we intend to / did publish
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER REFERENCES events(id),
    poster_path     TEXT,
    caption_text    TEXT,
    hashtags        TEXT,
    status          TEXT DEFAULT 'pending',  -- pending | published | failed | skipped
    platform        TEXT DEFAULT 'facebook', -- facebook | instagram | both
    fb_post_id      TEXT,
    ig_post_id      TEXT,
    error_message   TEXT,
    published_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- CAPTIONS: generated caption templates cache
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS captions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    template_key    TEXT NOT NULL,
    caption_text    TEXT NOT NULL,
    hashtags        TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- POST_HISTORY: deduplication log
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS post_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key       TEXT UNIQUE NOT NULL,   -- competition+match_id+event_type+minute
    caption_hash    TEXT,
    poster_hash     TEXT,
    posted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- ENGAGEMENT: analytics from Meta APIs
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS engagement (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER REFERENCES posts(id),
    fb_post_id      TEXT,
    platform        TEXT,
    likes           INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0,
    shares          INTEGER DEFAULT 0,
    reach           INTEGER DEFAULT 0,
    impressions     INTEGER DEFAULT 0,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- SETTINGS: runtime key-value store
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_events_event_id    ON events(event_id);
CREATE INDEX IF NOT EXISTS idx_events_match_id    ON events(match_id);
CREATE INDEX IF NOT EXISTS idx_posts_status       ON posts(status);
CREATE INDEX IF NOT EXISTS idx_post_history_key   ON post_history(event_key);
"""


def get_connection() -> sqlite3.Connection:
    """Return a configured SQLite connection."""
    conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    logger.info("Initialising database at %s", DB_PATH)
    with get_connection() as conn:
        conn.executescript(DDL)
    logger.info("Database ready.")


def set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES(?,?,CURRENT_TIMESTAMP)",
            (key, value)
        )


def get_setting(key: str, default=None):
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default
