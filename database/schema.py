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

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key   TEXT    NOT NULL UNIQUE,
    event_type  TEXT    NOT NULL,
    competition TEXT,
    match_id    TEXT,
    created_at  DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS post_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT    NOT NULL,
    content_type TEXT,
    posted_at    DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS match_state (
    match_id    TEXT    PRIMARY KEY,
    home_score  INTEGER NOT NULL DEFAULT 0,
    away_score  INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'NS',
    updated_at  DATETIME DEFAULT (datetime('now'))
);
"""

POSTS_COLUMNS = {
    "event_id":      "INTEGER DEFAULT 0",
    "poster_path":   "TEXT",
    "caption_text":  "TEXT",
    "hashtags":      "TEXT DEFAULT ''",
    "platform":      "TEXT DEFAULT 'facebook'",
    "status":        "TEXT DEFAULT 'pending'",
    "content_hash":  "TEXT",
    "content_type":  "TEXT",
    "competition":   "TEXT",
    "fb_post_id":    "TEXT",
    "ig_post_id":    "TEXT",
    "error_message": "TEXT",
    "likes":         "INTEGER DEFAULT 0",
    "comments":      "INTEGER DEFAULT 0",
    "shares":        "INTEGER DEFAULT 0",
    "posted_at":     "DATETIME DEFAULT (datetime('now'))",
    "published_at":  "DATETIME",
}


def get_connection() -> sqlite3.Connection:
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any missing columns to posts table — safe to run every startup."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
    for col, definition in POSTS_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {definition}")
            logger.info("Migration: added column posts.%s", col)


def init_db() -> None:
    """Create all tables and migrate any missing columns."""
    with get_connection() as conn:
        conn.executescript(DDL)
        _migrate(conn)
    logger.info("Database initialised at %s", DB_PATH)