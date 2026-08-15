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

CREATE TABLE IF NOT EXISTS engagement (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     INTEGER NOT NULL,
    fb_post_id  TEXT,
    likes       INTEGER DEFAULT 0,
    comments    INTEGER DEFAULT 0,
    shares      INTEGER DEFAULT 0,
    reach       INTEGER DEFAULT 0,
    checked_at  DATETIME DEFAULT (datetime('now')),
    FOREIGN KEY (post_id) REFERENCES posts(id)
);
"""

# Columns posts table must have (all nullable — publisher_agent doesn't fill all of them)
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


def _rebuild_posts_if_needed(conn: sqlite3.Connection) -> None:
    """
    If posts table has NOT NULL on content_hash (old schema), rebuild it.
    SQLite can't DROP constraints with ALTER TABLE, so we rename → recreate → copy.
    """
    # Check if content_hash has notnull=1
    cols = conn.execute("PRAGMA table_info(posts)").fetchall()
    needs_rebuild = any(col[1] == "content_hash" and col[3] == 1 for col in cols)
    if not needs_rebuild:
        return

    logger.info("Rebuilding posts table to remove NOT NULL on content_hash...")

    # Figure out which columns actually exist in the old table —
    # it may predate event_id/caption_text/status/etc, so we can't
    # assume the full POSTS_COLUMNS set is present.
    old_cols = {row[1] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}

    # Every column the new table wants, in a fixed order (id first).
    new_table_columns = [
        "id", "event_id", "poster_path", "caption_text", "hashtags",
        "platform", "status", "content_hash", "content_type", "competition",
        "fb_post_id", "ig_post_id", "error_message", "likes", "comments",
        "shares", "posted_at", "published_at",
    ]

    # Columns we can actually pull from posts_old (id always exists).
    copyable = [c for c in new_table_columns if c == "id" or c in old_cols]

    # Build SELECT expressions with sane defaults for numeric/date columns.
    select_exprs = []
    for c in copyable:
        if c in ("likes", "comments", "shares"):
            select_exprs.append(f"COALESCE({c},0)")
        elif c == "posted_at":
            select_exprs.append("COALESCE(posted_at, datetime('now'))")
        else:
            select_exprs.append(c)

    columns_sql = ", ".join(copyable)
    select_sql = ", ".join(select_exprs)

    conn.executescript(f"""
        PRAGMA foreign_keys=OFF;

        ALTER TABLE posts RENAME TO posts_old;

        CREATE TABLE posts (
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

        INSERT OR IGNORE INTO posts ({columns_sql})
        SELECT {select_sql}
        FROM posts_old;

        DROP TABLE posts_old;

        PRAGMA foreign_keys=ON;
    """)
    logger.info("posts table rebuilt successfully. Copied columns: %s", copyable)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any missing columns to posts table — safe to run every startup."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
    for col, definition in POSTS_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {definition}")
            logger.info("Migration: added column posts.%s", col)


def init_db() -> None:
    """Create tables, fix schema issues, migrate missing columns."""
    with get_connection() as conn:
        conn.executescript(DDL)
        _rebuild_posts_if_needed(conn)
        _migrate(conn)
    logger.info("Database initialised at %s", DB_PATH)
