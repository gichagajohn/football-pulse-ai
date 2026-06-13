#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from database.schema import init_db
from utils.logger import setup_logger
log = setup_logger('run_once')

def main():
    log.info('=== Football Pulse AI cycle starting ===')
    init_db()
    try:
        from agents.scheduler_agent import check_live_matches
        check_live_matches()
    except Exception as e:
        log.error('Live matches: %s', e)
    try:
        from agents.scheduler_agent import post_todays_fixtures
        post_todays_fixtures()
    except Exception as e:
        log.error('Fixtures: %s', e)
    try:
        from agents.injury_transfer_agent import scan_for_news
        scan_for_news()
    except Exception as e:
        log.error('News: %s', e)
    try:
        from agents.scheduler_agent import post_football_fact
        post_football_fact()
    except Exception as e:
        log.error('Fact: %s', e)
    try:
        from agents.scheduler_agent import post_on_this_day
        post_on_this_day()
    except Exception as e:
        log.error('OTD: %s', e)
    try:
        from agents.analytics_agent import update_all_engagement, log_summary
        update_all_engagement()
        log_summary()
    except Exception as e:
        log.error('Analytics: %s', e)
    log.info('=== Cycle complete ===')

if __name__ == '__main__':
    main()
