#!/usr/bin/env python3

"""
run_once.py — Football Pulse AI

Runs one scheduled job for GitHub Actions.

Supported jobs:
    live
    fixtures
    news
    results
    all
"""

import os
import sys
from datetime import datetime

import pytz

# Ensure the repository root is available on the Python path.
sys.path.insert(0, os.path.dirname(__file__))

from database.schema import init_db
from utils.logger import setup_logger


log = setup_logger("run_once")

EAT = pytz.timezone("Africa/Nairobi")


def job_live():
    """
    Poll live matches once and publish any newly detected goal alerts.
    """
    log.info("=== JOB: LIVE GOAL MONITOR ===")

    from agents.scheduler_agent import check_live_matches

    check_live_matches()


def job_fixtures():
    """
    Post today's fixtures.
    """
    log.info("=== JOB: TODAY'S FIXTURES ===")

    from agents.scheduler_agent import post_todays_fixtures

    post_todays_fixtures()


def job_news():
    """
    Scan and publish transfer or injury news.
    """
    log.info("=== JOB: TRANSFER AND INJURY NEWS ===")

    from agents.injury_transfer_agent import scan_for_news

    scan_for_news()


def job_results():
    """
    Post today's full-time results summary.
    """
    log.info("=== JOB: TODAY'S RESULTS ===")

    from agents.scheduler_agent import post_todays_results

    post_todays_results()


def job_all():
    """
    Run the normal daily content jobs.
    """
    log.info("=== JOB: ALL DAILY TASKS ===")

    job_fixtures()
    job_news()
    job_results()


def automatic_job():
    """
    Select a job based on the current time in Nairobi.

    This is used when BOT_JOB is not provided.
    """
    hour = datetime.now(EAT).hour

    log.info("Current Nairobi time hour: %s", hour)

    if hour == 8:
        job_fixtures()

    elif hour in (11, 15, 18):
        job_news()

    elif hour == 0:
        job_results()

    else:
        # Outside the normal daily schedule, use the cycle for
        # live-score and goal monitoring.
        job_live()


def main():
    log.info("=== Football Pulse AI starting ===")

    # Make sure all tables exist before any job runs.
    init_db()

    forced_job = os.getenv("BOT_JOB", "").strip().lower()

    try:
        if forced_job == "live":
            job_live()

        elif forced_job == "fixtures":
            job_fixtures()

        elif forced_job == "news":
            job_news()

        elif forced_job == "results":
            job_results()

        elif forced_job == "all":
            job_all()

        else:
            automatic_job()

    except Exception:
        log.exception("Football Pulse job failed")
        raise

    log.info("=== Football Pulse job complete ===")


if __name__ == "__main__":
    main()
