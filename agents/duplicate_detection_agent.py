"""
agents/duplicate_detection_agent.py — Football Pulse AI
Standalone duplicate detection agent.
Wraps content_decision_agent dedup functions with a clean public API
and includes a self-test runner.
"""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

import settings
from database.schema import get_connection, init_db
from utils.logger import setup_logger

logger = setup_logger("dedup_agent")


# ─────────────────────────────────────────────────────────────────────────────
# Core hashing
# ─────────────────────────────────────────────────────────────────────────────

def hash_text(text: str) -> str:
    """SHA-256 hash truncated to 16 hex chars."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def hash_file(path: str) -> Optional[str]:
    """MD5 hash of a file (for poster dedup). Returns None if file missing."""
    try:
        import hashlib
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except FileNotFoundError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Event key builder
# ─────────────────────────────────────────────────────────────────────────────

def build_event_key(
    match_id: str,
    event_type: str,
    minute: Optional[int] = None,
    player: Optional[str] = None,
    extra: Optional[str] = None,
) -> str:
    """
    Build a deterministic, collision-resistant event key.
    Examples:
      GOAL:      "98765:GOAL:87:salah"
      FULLTIME:  "98765:FULLTIME"
      STANDINGS: "PL:LEAGUE_TABLE:20240315"
    """
    parts = [str(match_id), event_type.upper()]
    if minute is not None:
        parts.append(str(minute))
    if player:
        parts.append(player.strip().lower().replace(" ", "_"))
    if extra:
        parts.append(str(extra))
    return ":".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def is_duplicate(
    match_id: str,
    event_type: str,
    minute: Optional[int] = None,
    player: Optional[str] = None,
    extra: Optional[str] = None,
) -> bool:
    """
    Returns True if this event was already posted within DEDUPE_WINDOW_HOURS.
    Thread-safe (SQLite WAL mode).
    """
    key    = build_event_key(match_id, event_type, minute, player, extra)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.DEDUPE_WINDOW_HOURS)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM post_history WHERE event_key = ? AND posted_at > ?",
            (key, cutoff.isoformat()),
        ).fetchone()

    if row:
        logger.debug("Duplicate blocked: %s", key)
        return True
    return False


def record(
    match_id: str,
    event_type: str,
    minute: Optional[int] = None,
    player: Optional[str] = None,
    caption: Optional[str] = None,
    poster_path: Optional[str] = None,
    extra: Optional[str] = None,
):
    """Mark an event as published so it won't be posted again."""
    key          = build_event_key(match_id, event_type, minute, player, extra)
    caption_hash = hash_text(caption)    if caption     else None
    poster_hash  = hash_file(poster_path) if poster_path else None

    with get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO post_history(event_key, caption_hash, poster_hash)
               VALUES (?, ?, ?)""",
            (key, caption_hash, poster_hash),
        )
    logger.debug("Post recorded: %s", key)


def clear_expired():
    """Remove post_history entries older than DEDUPE_WINDOW_HOURS (housekeeping)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.DEDUPE_WINDOW_HOURS)
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM post_history WHERE posted_at < ?",
            (cutoff.isoformat(),)
        )
        deleted = cur.rowcount
    if deleted:
        logger.info("Cleared %d expired dedup records.", deleted)


def get_stats() -> dict:
    """Return dedup table statistics."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM post_history").fetchone()[0]
        recent = conn.execute(
            "SELECT COUNT(*) FROM post_history WHERE posted_at > ?",
            ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),)
        ).fetchone()[0]
    return {"total_records": total, "last_24h": recent}


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

def run_tests():
    """Quick smoke-test of the dedup system. Run: python -m agents.duplicate_detection_agent"""
    import tempfile, os
    print("\n── Duplicate Detection Agent — Self Test ──\n")

    # Use an in-memory temp DB for tests
    original_db = settings.DB_PATH
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    # Monkey-patch path for test
    import database.schema as schema_mod
    schema_mod.DB_PATH = tmp.name
    settings.DB_PATH   = tmp.name
    init_db()

    try:
        # Test 1: Fresh event is NOT a duplicate
        assert not is_duplicate("M001", "GOAL", 23, "Salah"), "FAIL: fresh event flagged as dup"
        print("✅ Test 1 passed: fresh event not flagged as duplicate")

        # Test 2: Record the event
        record("M001", "GOAL", 23, "Salah", caption="Test caption")
        print("✅ Test 2 passed: event recorded successfully")

        # Test 3: Same event IS now a duplicate
        assert is_duplicate("M001", "GOAL", 23, "Salah"), "FAIL: dup not detected after record"
        print("✅ Test 3 passed: duplicate correctly detected")

        # Test 4: Different minute = NOT duplicate
        assert not is_duplicate("M001", "GOAL", 67, "Salah"), "FAIL: different minute flagged as dup"
        print("✅ Test 4 passed: different minute not flagged")

        # Test 5: Different match = NOT duplicate
        assert not is_duplicate("M002", "GOAL", 23, "Salah"), "FAIL: different match flagged as dup"
        print("✅ Test 5 passed: different match not flagged")

        # Test 6: Different event type = NOT duplicate
        assert not is_duplicate("M001", "FULLTIME", None, None), "FAIL: different type flagged as dup"
        print("✅ Test 6 passed: different event type not flagged")

        # Test 7: Stats
        stats = get_stats()
        assert stats["total_records"] == 1, f"FAIL: expected 1 record, got {stats['total_records']}"
        print(f"✅ Test 7 passed: stats correct — {stats}")

        # Test 8: Hash functions
        h1 = hash_text("hello world")
        h2 = hash_text("hello world")
        h3 = hash_text("different")
        assert h1 == h2, "FAIL: same input gives different hashes"
        assert h1 != h3, "FAIL: different inputs give same hash"
        print("✅ Test 8 passed: hashing stable and collision-free")

        print("\n🎉 All tests passed!\n")

    finally:
        schema_mod.DB_PATH = original_db
        settings.DB_PATH   = original_db
        os.unlink(tmp.name)


if __name__ == "__main__":
    run_tests()
