#!/usr/bin/env python3
"""
run_once.py — Football Pulse AI
Runs the correct job based on current EAT time.

Schedule (EAT = UTC+3):
  08:00  →  fixtures job   (post today's upcoming matches)
  11:00  →  news job       (transfer & injury news)
  15:00  →  news job       (transfer & injury news)
  18:00  →  news job       (transfer & injury news)
  00:00  →  results job    (full-time results from today)

When triggered manually via workflow_dispatch with job=all, runs everything.
"""

import sys
import os
from datetime import datetime
import pytz

sys.path.insert(0, os.path.dirname(__file__))

from database.schema import init_db
from utils.logger import setup_logger

log = setup_logger("run_once")

EAT = pytz.timezone("Africa/Nairobi")


def _current_eat_hour() -> int:
    return datetime.now(EAT).hour


def job_fixtures():
    """8:00 AM EAT — post today's fixtures."""
    log.info("=== JOB: TODAY'S FIXTURES ===")
    try:
        from agents.scheduler_agent import post_todays_fixtures
        post_todays_fixtures()
    except Exception as e:
        log.error("Fixtures job failed: %s", e)


def job_news():
    """11:00 AM / 3:00 PM / 6:00 PM EAT — transfer & injury news."""
    log.info("=== JOB: TRANSFER & INJURY NEWS ===")
    try:
        from agents.injury_transfer_agent import scan_for_news
        scan_for_news()
    except Exception as e:
        log.error("News job failed: %s", e)


def job_results():
    """Midnight EAT — post full-time results from today."""
    log.info("=== JOB: TODAY'S RESULTS ===")
    try:
        from agents.scheduler_agent import post_todays_results
        post_todays_results()
    except Exception as e:
        log.error("Results job failed: %s", e)


def job_all():
    """Manual trigger — run everything."""
    log.info("=== JOB: ALL (manual trigger) ===")
    job_fixtures()
    job_news()
    job_results()


def main():
    log.info("=== Football Pulse AI starting ===")
    init_db()

    # Check if a specific job was requested via environment variable
    # (set by workflow_dispatch input)
    forced_job = os.getenv("BOT_JOB", "").strip().lower()

    if forced_job == "fixtures":
        job_fixtures()
    elif forced_job == "news":
        job_news()
    elif forced_job == "results":
        job_results()
    elif forced_job == "all":
        job_all()
    else:
        # Auto-detect based on current EAT hour
        hour = _current_eat_hour()
        log.info("Current EAT hour: %d", hour)

        if hour == 8:
            job_fixtures()
        elif hour in (11, 15, 18):
            job_news()
        elif hour == 0:
            job_results()
        else:
            # Fallback: shouldn't happen with the cron schedule,
            # but run news as a safe default
            log.info("Hour %d not mapped to a specific job — running news as fallback.", hour)
            job_news()

    log.info("=== Cycle complete ===")


if __name__ == "__main__":
    main()
