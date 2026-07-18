#!/usr/bin/env python3
"""
cli.py — Football Pulse AI
Command-line tool for manual testing, one-off posts, and system diagnostics.

Usage:
  python cli.py test-posters          # Generate all poster types with sample data
  python cli.py test-captions         # Print sample captions
  python cli.py test-dedup            # Run duplicate detection tests
  python cli.py stats                 # Show analytics summary
  python cli.py post-fact             # Manually trigger a football fact post
  python cli.py post-fixtures         # Manually trigger today's fixtures post
  python cli.py clear-dedup           # Clear dedup history (use carefully!)
  python cli.py db-status             # Show database record counts
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


def _require_db():
    from database.schema import init_db
    init_db()


def cmd_test_posters():
    print("Generating all poster types…")
    os.system(f"{sys.executable} test_posters.py")


def cmd_test_captions():
    from agents import caption_agent as ca
    print("\n── GOAL CAPTION ──────────────────────────────────")
    print(ca.generate_goal_caption("Mohamed Salah", "Liverpool", "Liverpool", "Arsenal", 2, 1, 87, "Premier League", "Trent Alexander-Arnold"))
    print("\n── FULLTIME CAPTION ──────────────────────────────")
    print(ca.generate_fulltime_caption("Liverpool", "Arsenal", 2, 1, "Premier League",
        [{"team":"home","player":"Salah","minute":23},{"team":"home","player":"Diaz","minute":71},{"team":"away","player":"Saka","minute":88}]))
    print("\n── TRANSFER CAPTION ──────────────────────────────")
    print(ca.generate_transfer_caption("Kylian Mbappé", "PSG", "Real Madrid", "Free Transfer"))
    print("\n── MATCHDAY CAPTION ──────────────────────────────")
    print(ca.generate_matchday_caption("Real Madrid", "Barcelona", "20:45", "La Liga", "Santiago Bernabéu"))
    print("\n── FACT CAPTION ──────────────────────────────────")
    print(ca.generate_fact_caption("Pelé scored 1,281 goals in 1,363 games throughout his career."))


def cmd_test_dedup():
    _require_db()
    from agents.duplicate_detection_agent import run_tests
    run_tests()


def cmd_stats():
    _require_db()
    from agents.analytics_agent import get_summary_stats
    from database.schema import get_connection
    stats = get_summary_stats()
    print("\n📊 Football Pulse AI — Analytics Summary")
    print("=" * 40)
    print(f"  Posts published : {stats['total_posts']}")
    print(f"  Total likes     : {stats['total_likes']}")
    print(f"  Total comments  : {stats['total_comments']}")
    print(f"  Total shares    : {stats['total_shares']}")

    with get_connection() as conn:
        pending = conn.execute("SELECT COUNT(*) FROM posts WHERE status='pending'").fetchone()[0]
        failed  = conn.execute("SELECT COUNT(*) FROM posts WHERE status='failed'").fetchone()[0]
        dedup   = conn.execute("SELECT COUNT(*) FROM post_history").fetchone()[0]
    print(f"  Pending posts   : {pending}")
    print(f"  Failed posts    : {failed}")
    print(f"  Dedup records   : {dedup}")
    print()


def cmd_post_fact():
    _require_db()
    from agents.scheduler_agent import post_football_fact
    print("Posting a football fact…")
    post_football_fact()
    print("Done.")


def cmd_post_fixtures():
    _require_db()
    from agents.scheduler_agent import post_todays_fixtures
    print("Posting today's fixtures…")
    post_todays_fixtures()
    print("Done.")


def cmd_clear_dedup():
    _require_db()
    confirm = input("⚠️  This clears all dedup history. Type YES to confirm: ")
    if confirm.strip() == "YES":
        from database.schema import get_connection
        with get_connection() as conn:
            conn.execute("DELETE FROM post_history")
        print("✅ Dedup history cleared.")
    else:
        print("Cancelled.")


def cmd_db_status():
    _require_db()
    from database.schema import get_connection
    tables = ["events", "posts", "captions", "post_history", "engagement", "settings"]
    print("\n🗄️  Database Status")
    print("=" * 35)
    with get_connection() as conn:
        for t in tables:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t:<20} {n:>6} rows")
            except Exception as e:
                print(f"  {t:<20} ERROR: {e}")
    print()


COMMANDS = {
    "test-posters":  cmd_test_posters,
    "test-captions": cmd_test_captions,
    "test-dedup":    cmd_test_dedup,
    "stats":         cmd_stats,
    "post-fact":     cmd_post_fact,
    "post-fixtures": cmd_post_fixtures,
    "clear-dedup":   cmd_clear_dedup,
    "db-status":     cmd_db_status,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(0)
    COMMANDS[sys.argv[1]]()
