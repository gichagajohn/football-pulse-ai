"""
agents/scheduler_agent.py — Football Pulse AI
Orchestrates all recurring jobs using APScheduler.
Match state is now persisted in the match_state DB table so goal/fulltime
detection works correctly across GitHub Actions runs.
"""

import json
import random
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

import settings
from utils.logger import setup_logger
from database.schema import get_connection, init_db

log = setup_logger("scheduler_agent")

# ── helpers ──────────────────────────────────────────────────────────────────

def _get_prev_state(match_id: str) -> dict | None:
    """Load the last-known score/status for a match from the DB."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT home_score, away_score, status FROM match_state WHERE match_id = ?",
            (match_id,),
        ).fetchone()
    if row is None:
        return None
    return {"home": row["home_score"], "away": row["away_score"], "status": row["status"]}


def _save_state(match_id: str, home: int, away: int, status: str) -> None:
    """Upsert the current score/status for a match into the DB."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO match_state (match_id, home_score, away_score, status, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(match_id) DO UPDATE SET
                   home_score = excluded.home_score,
                   away_score = excluded.away_score,
                   status     = excluded.status,
                   updated_at = excluded.updated_at""",
            (match_id, home, away, status),
        )


# ── live match logic ──────────────────────────────────────────────────────────

def _handle_goal(match: dict, home_score: int, away_score: int) -> None:
    """Post a goal update."""
    try:
        from agents.poster_agent import post_goal_update
        from agents.content_decision_agent import should_post, record_post
        competition = match.get("competition", {}).get("name", "default")
        mid = str(match.get("id", ""))
        key = f"{mid}:{home_score}:{away_score}"
        if should_post("GOAL", competition, dedup_key=key):
            fb_id = post_goal_update(match, home_score, away_score)
            record_post("GOAL", key, competition, fb_id)
            log.info("Goal posted for match %s (%d-%d)", mid, home_score, away_score)
    except Exception as exc:
        log.error("_handle_goal error: %s", exc)


def _handle_fulltime(match: dict, home_score: int, away_score: int) -> None:
    """Post a full-time result."""
    try:
        from agents.poster_agent import post_fulltime_result
        from agents.content_decision_agent import should_post, record_post
        competition = match.get("competition", {}).get("name", "default")
        mid = str(match.get("id", ""))
        key = f"FT:{mid}"
        if should_post("FULLTIME", competition, dedup_key=key):
            fb_id = post_fulltime_result(match, home_score, away_score)
            record_post("FULLTIME", key, competition, fb_id)
            log.info("Full-time posted for match %s (%d-%d)", mid, home_score, away_score)
    except Exception as exc:
        log.error("_handle_fulltime error: %s", exc)


def check_live_matches() -> None:
    """
    Fetch live matches from the API and compare against persisted state.
    Goals and full-time results are detected by diffing current vs last-known score.
    """
    try:
        from agents.football_data_agent import get_live_matches
        matches = get_live_matches()
        log.info("Live matches fetched: %d", len(matches))
    except Exception as exc:
        log.error("check_live_matches fetch error: %s", exc)
        return

    for match in matches:
        try:
            mid = str(match.get("id", ""))
            score = match.get("score", {})
            ft = score.get("fullTime", {})
            home_score = ft.get("home") or 0
            away_score = ft.get("away") or 0
            status = match.get("status", "")

            prev = _get_prev_state(mid)

            if prev is None:
                # First time we've seen this match — just record the baseline
                log.info("New match seen: %s (status=%s, score=%d-%d) — recording baseline",
                         mid, status, home_score, away_score)
                _save_state(mid, home_score, away_score, status)
                continue

            # Detect goal
            if home_score + away_score > prev["home"] + prev["away"]:
                log.info("Goal detected in match %s: %d-%d (was %d-%d)",
                         mid, home_score, away_score, prev["home"], prev["away"])
                _handle_goal(match, home_score, away_score)

            # Detect full-time
            if status in ("FINISHED", "FT") and prev["status"] not in ("FINISHED", "FT"):
                log.info("Full-time detected in match %s: %d-%d", mid, home_score, away_score)
                _handle_fulltime(match, home_score, away_score)

            # Always update saved state
            _save_state(mid, home_score, away_score, status)

        except Exception as exc:
            log.error("check_live_matches loop error for match %s: %s",
                      match.get("id", "?"), exc)


# ── other scheduled jobs ──────────────────────────────────────────────────────

def post_todays_fixtures() -> None:
    try:
        from agents.fixture_agent import fetch_and_post_fixtures
        fetch_and_post_fixtures()
        log.info("Fixtures job done")
    except Exception as exc:
        log.error("post_todays_fixtures: %s", exc)


def post_football_fact() -> None:
    try:
        from agents.fact_agent import post_random_fact
        post_random_fact()
        log.info("Fact job done")
    except Exception as exc:
        log.error("post_football_fact: %s", exc)


def post_on_this_day() -> None:
    try:
        from agents.otd_agent import post_on_this_day_event
        post_on_this_day_event()
        log.info("OTD job done")
    except Exception as exc:
        log.error("post_on_this_day: %s", exc)


# ── scheduler entry-point (used when running as a long-lived process) ─────────

def run_scheduler() -> None:
    init_db()
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(check_live_matches,    IntervalTrigger(minutes=2),  id="live")
    scheduler.add_job(post_todays_fixtures,  IntervalTrigger(hours=6),    id="fixtures")
    scheduler.add_job(post_football_fact,    IntervalTrigger(hours=8),    id="fact")
    scheduler.add_job(post_on_this_day,      IntervalTrigger(hours=24),   id="otd")

    log.info("Scheduler started")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


if __name__ == "__main__":
    run_scheduler()