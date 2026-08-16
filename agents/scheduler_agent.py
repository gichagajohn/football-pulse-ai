"""
agents/scheduler_agent.py — Football Pulse AI
Orchestrates all recurring jobs.
Changes:
  - Football facts: once per day only
  - On This Day: once per day only
  - Fixture kickoff times displayed in EAT (Africa/Nairobi, UTC+3)
"""

import json
import random
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz

import settings
from database.schema import get_connection
from utils.logger import setup_logger

from agents import football_data_agent    as data_agent
from agents import content_decision_agent as decision_agent
from agents import poster_design_agent    as poster_agent
from agents import caption_agent
from agents import publisher_agent
from agents import analytics_agent

logger = setup_logger("scheduler_agent")

TZ = pytz.timezone(settings.TIMEZONE)   # Africa/Nairobi = UTC+3

_previous_scores: dict = {}


# ─────────────────────────────────────────────────────────────────────────────
# Live match handling
# ─────────────────────────────────────────────────────────────────────────────

def check_live_matches():
    try:
        matches = data_agent.get_live_matches()
    except Exception as e:
        logger.warning("Live match fetch failed: %s", e)
        return

    logger.info("Live matches to process: %d", len(matches))

    for raw in matches:
        match = data_agent.normalise_match(raw)
        mid    = match["match_id"]
        home   = match["home_score"]
        away   = match["away_score"]
        status = match["status"]
        comp   = match["competition"]

        prev = _previous_scores.get(mid)

        if prev is None:
            logger.info("New match baseline: %s [%s] %s %d-%d",
                        mid, comp, status, home, away)
        else:
            if home > prev[0] or away > prev[1]:
                scoring_team = match["home_team"] if home > prev[0] else match["away_team"]
                _handle_goal(match, scoring_team)

            if prev[2] not in ("FINISHED", "FULL_TIME") and status in ("FINISHED", "FULL_TIME"):
                _handle_fulltime(match)

        _previous_scores[mid] = (home, away, status)


def _handle_goal(match: dict, scoring_team: str):
    mid    = match["match_id"]
    comp   = match["competition"]
    home   = match["home_score"]
    away   = match["away_score"]
    minute = match.get("minute") or 0

    event_id = f"GOAL_{mid}_{home}_{away}"

    if decision_agent.is_duplicate(event_id, "GOAL"):
        return

    should, priority = decision_agent.should_post("GOAL", comp)
    if not should or not decision_agent.within_rate_limit():
        return

    try:
        poster_path = poster_agent.create_goal_alert(
            home_team  = match["home_team"],
            away_team  = match["away_team"],
            home_score = home,
            away_score = away,
            scorer     = scoring_team,
            minute     = minute,
            competition= comp,
        )
        cap = caption_agent.generate_goal_caption(
            scorer     = scoring_team,
            team       = scoring_team,
            home_team  = match["home_team"],
            away_team  = match["away_team"],
            home_score = home,
            away_score = away,
            minute     = minute,
            competition= comp,
        )
        db_id = publisher_agent.create_post_record(None, poster_path, cap)
        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(event_id, "GOAL", None, None, cap, str(poster_path))
        logger.info("Goal posted: %s %d-%d", comp, home, away)

    except Exception as e:
        logger.exception("Goal handling error: %s", e)


def _handle_fulltime(match: dict):
    mid  = match["match_id"]
    comp = match["competition"]

    if decision_agent.is_duplicate(mid, "FULLTIME"):
        return

    should, priority = decision_agent.should_post("FULLTIME", comp)
    if not should or not decision_agent.within_rate_limit():
        return

    try:
        poster_path = poster_agent.create_fulltime(
            home_team  = match["home_team"],
            away_team  = match["away_team"],
            home_score = match["home_score"],
            away_score = match["away_score"],
            competition= comp,
        )
        cap = caption_agent.generate_fulltime_caption(
            home_team  = match["home_team"],
            away_team  = match["away_team"],
            home_score = match["home_score"],
            away_score = match["away_score"],
            competition= comp,
        )
        db_id = publisher_agent.create_post_record(None, poster_path, cap)
        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(mid, "FULLTIME", None, None, cap, str(poster_path))
        logger.info("Full-time posted: %s %d-%d", comp,
                    match["home_score"], match["away_score"])

    except Exception as e:
        logger.exception("Full-time handling error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures  (kickoff times in EAT = UTC+3)
# ─────────────────────────────────────────────────────────────────────────────

def post_todays_fixtures():
    logger.info("Generating today's fixtures post...")
    try:
        today_key = datetime.now(TZ).strftime("%Y%m%d")

        if decision_agent.is_duplicate(today_key, "TODAYS_FIXTURES"):
            logger.info("Fixtures already posted today.")
            return

        raw_fixtures = data_agent.get_todays_fixtures()
        if not raw_fixtures:
            logger.info("No fixtures today.")
            return

        fixtures = []
        for raw in raw_fixtures:
            m = data_agent.normalise_match(raw)
            dt_str = raw.get("utcDate", "")
            try:
                from datetime import datetime as dt_cls
                kickoff_utc   = dt_cls.fromisoformat(dt_str.replace("Z", "+00:00"))
                kickoff_eat   = kickoff_utc.astimezone(TZ)
                kickoff_local = kickoff_eat.strftime("%H:%M EAT")
            except Exception:
                kickoff_local = "TBC"

            fixtures.append({
                "home_team":    m["home_team"],
                "away_team":    m["away_team"],
                "kickoff_time": kickoff_local,
                "competition":  m["competition"],
            })

        poster_path = poster_agent.create_todays_fixtures(fixtures)
        cap = (
            "TODAY'S FOOTBALL FIXTURES\n\n"
            "Here is what is on today! All times in EAT.\n\n"
            "#Football #TodaysFixtures #FootballPulse #Matchday"
        )

        db_id = publisher_agent.create_post_record(None, poster_path, cap)
        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(today_key, "TODAYS_FIXTURES",
                                   None, None, cap, str(poster_path))
        logger.info("Fixtures posted: %d matches across %d competitions",
                    len(fixtures),
                    len(set(f["competition"] for f in fixtures)))

    except Exception as e:
        logger.exception("Today's fixtures error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Football facts  — ONCE PER DAY
# ─────────────────────────────────────────────────────────────────────────────

FOOTBALL_FACTS = [
    "The fastest goal in Premier League history was scored by Shane Long in just 7.69 seconds against Watford in 2019.",
    "Pele scored his 1,000th goal in professional football on November 19, 1969.",
    "The longest unbeaten run in English football belongs to Arsenal's Invincibles - 49 matches unbeaten (2003-2004).",
    "Messi has won more Ballon d'Or awards than any other player in history - 8 times.",
    "The first ever FIFA World Cup was held in Uruguay in 1930. Uruguay won it.",
    "Ronaldo is the all-time top scorer in men's international football with over 130 goals.",
    "Real Madrid has won the UEFA Champions League more than any other club - 15 times.",
    "Liverpool's Steven Gerrard never won the Premier League despite 17 seasons at the club.",
    "The most expensive transfer in football history is Neymar's move to PSG for 222 million euros in 2017.",
    "Brazil is the only team to have played in every FIFA World Cup.",
    "The biggest recorded win in football history is Australia's 31-0 defeat of American Samoa in 2001.",
    "Goalkeeper Dino Zoff won the World Cup at age 40 with Italy in 1982 - the oldest winner ever.",
    "Manchester United won the treble in 1999 under Sir Alex Ferguson: Premier League, FA Cup, and Champions League.",
    "The fastest red card in history was shown to Lee Todd just 2 seconds after kick-off.",
    "Cristiano Ronaldo is the first player to score in 5 different FIFA World Cups.",
    "Lionel Messi finally won the FIFA World Cup with Argentina in Qatar 2022.",
    "The 2026 FIFA World Cup is the first to be hosted by 3 countries: USA, Canada, and Mexico.",
    "Lev Yashin is the only goalkeeper to ever win the Ballon d'Or, in 1963.",
    "The record attendance for a football match is 199,854 at the 1950 World Cup final in Brazil.",
    "Bayern Munich once won the Bundesliga by 25 points in the 2012-13 season.",
    "Pele is the only player to have won 3 FIFA World Cups (1958, 1962, 1970).",
    "The Champions League anthem was composed by Tony Britten in 1992.",
    "Manchester City won the Premier League with a record 100 points in the 2017-18 season.",
    "Kylian Mbappe became the second teenager to score in a World Cup final in 2018.",
    "Italy went unbeaten for 37 games before losing to Spain at Euro 2020.",
    "The fastest hat-trick in Premier League history was scored by Sadio Mane in just 2 minutes 56 seconds.",
    "The first World Cup to use VAR technology was Russia 2018.",
    "Oliver Kahn is the only goalkeeper to win the Golden Ball at a FIFA World Cup (2002).",
    "Arsenal went an entire Premier League season unbeaten in 2003-04, earning the nickname The Invincibles.",
    "Gerd Muller scored 85 goals in just 62 games for West Germany.",
    "The penalty shootout was introduced to the World Cup in 1978.",
    "Roberto Carlos scored one of the greatest free kicks ever against France in 1997.",
    "Zinedine Zidane won the World Cup, European Championship, Champions League, and Ballon d'Or.",
    "FC Barcelona's La Masia academy produced Messi, Xavi, Iniesta, and Puyol all at the same time.",
    "Ghana was the last African team to reach a World Cup quarter-final, in 2010.",
    "Sweden's Zlatan Ibrahimovic never played in a FIFA World Cup despite a legendary club career.",
    "The first football club in the world is Sheffield FC, founded in 1857.",
    "Andres Iniesta scored the winning goal in the 2010 World Cup final for Spain.",
    "Sir Alex Ferguson managed Manchester United for 26 years, winning 13 Premier League titles.",
    "The ball used in the 1930 World Cup final was different in each half - one from each country.",
    "N'Golo Kante won the World Cup with France and the Champions League with Chelsea in the same year.",
    "Jurgen Klopp's Liverpool went 30 years without a league title before winning in 2020.",
    "The highest scoring World Cup game ever was Austria 7-5 Switzerland in 1954.",
    "Mohamed Salah is the fastest player to reach 100 Premier League goals.",
    "The first women's FIFA World Cup was held in China in 1991. USA won it.",
    "Erling Haaland scored 36 Premier League goals in his debut season - a new record.",
    "Diego Maradona's Hand of God goal against England in 1986 is one of the most controversial moments in football.",
    "France became World Champions in 1998 on home soil, beating Brazil 3-0 in the final.",
    "Roger Milla became the oldest player to score at a World Cup at age 42 in 1994.",
    "The term hat-trick originated in cricket but was adopted by football in the 1800s.",
    "AC Milan and Inter Milan both play at the same stadium - the San Siro.",
    "Thierry Henry is Arsenal's all-time top scorer with 228 goals.",
    "Portugal's Eusebio scored 9 goals at the 1966 World Cup.",
    "Kevin De Bruyne is considered one of the greatest playmakers in Premier League history.",
    "Vinicius Jr won the Ballon d'Or in 2024, becoming Brazil's first winner since Ronaldo in 1997.",
    "The 2022 World Cup in Qatar was the first held in the Middle East.",
    "Japan beat Germany and Spain at the 2022 World Cup in one of football's biggest upsets.",
    "Morocco became the first African nation to reach the World Cup semi-finals in 2022.",
    "Didier Drogba is Ivory Coast's greatest ever footballer and a Chelsea legend.",
    "Liverpool's incredible comeback from 3-0 down to beat AC Milan in the 2005 Champions League final is known as the Miracle of Istanbul.",
]


def post_football_fact():
    """Post one football fact per day maximum."""
    logger.debug("Generating football fact post...")
    try:
        # Once-per-day dedup key
        today_key = datetime.now(TZ).strftime("%Y%m%d")
        fact_day_key = f"FACT_DAY_{today_key}"

        if decision_agent.is_duplicate(fact_day_key, "FOOTBALL_FACT_DAY"):
            logger.info("Football fact already posted today — skipping.")
            return

        # Pick a random fact that hasn't been posted within the dedup window
        random.shuffle(FOOTBALL_FACTS)
        for fact in FOOTBALL_FACTS:
            fact_key = f"FACT_{hash(fact) % 999999}"
            if not decision_agent.is_duplicate(fact_key, "FOOTBALL_FACT"):
                poster_path = poster_agent.create_football_fact(fact)
                cap = caption_agent.generate_fact_caption(fact)
                db_id = publisher_agent.create_post_record(None, poster_path, cap)
                publisher_agent.publish(poster_path, cap, post_id_db=db_id)

                # Record both the specific fact AND the daily limit
                decision_agent.record_post(fact_key, "FOOTBALL_FACT",
                                           None, None, cap, str(poster_path))
                decision_agent.record_post(fact_day_key, "FOOTBALL_FACT_DAY")
                logger.info("Fact posted.")
                return

        logger.info("All facts recently posted, skipping.")

    except Exception as e:
        logger.exception("Football fact error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# On This Day  — ONCE PER DAY
# ─────────────────────────────────────────────────────────────────────────────

def post_on_this_day():
    """Post one On This Day event per day maximum."""
    logger.debug("Generating On This Day post...")
    try:
        now = datetime.now(TZ)
        today_key = now.strftime("%Y%m%d")
        otd_day_key = f"OTD_DAY_{today_key}"

        if decision_agent.is_duplicate(otd_day_key, "ON_THIS_DAY_DAY"):
            logger.info("On This Day already posted today — skipping.")
            return

        events = data_agent.get_historical_fact_by_date(now.month, now.day)
        if not events:
            logger.info("No On This Day event for %s", now.strftime("%m-%d"))
            return

        event  = random.choice(events)
        name   = event.get("strEvent", "")
        season = event.get("strSeason", "")
        result = event.get("intHomeScore", "?")
        if not name:
            return

        fact    = f"On this day in {season}: {name} - {result}"
        key     = f"OTD_{now.strftime('%m%d')}_{hash(name) % 9999}"

        if decision_agent.is_duplicate(key, "ON_THIS_DAY"):
            return

        poster_path = poster_agent.create_football_fact(
            fact, category="ON THIS DAY", emoji=""
        )
        cap = (
            f"ON THIS DAY IN FOOTBALL\n\n{fact}\n\n"
            f"#OnThisDay #FootballHistory #FootballPulse"
        )
        db_id = publisher_agent.create_post_record(None, poster_path, cap)
        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(key, "ON_THIS_DAY", None, None, cap, str(poster_path))
        decision_agent.record_post(otd_day_key, "ON_THIS_DAY_DAY")
        logger.info("On This Day posted.")

    except Exception as e:
        logger.exception("On This Day error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────

def refresh_analytics():
    logger.debug("Refreshing engagement analytics...")
    try:
        analytics_agent.update_all_engagement()
        analytics_agent.log_summary()
    except Exception as e:
        logger.warning("Analytics refresh error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler (used when running as a long-lived process, not via run_once.py)
# ─────────────────────────────────────────────────────────────────────────────

def _scan_injury_transfer_news():
    from agents.injury_transfer_agent import scan_for_news
    try:
        scan_for_news()
    except Exception as e:
        logger.warning("Injury/transfer scan error: %s", e)


def start():
    from database.schema import init_db
    init_db()

    scheduler = BlockingScheduler(timezone=TZ)
    scheduler.add_job(check_live_matches,        IntervalTrigger(seconds=settings.LIVE_CHECK_INTERVAL),       id="live",      max_instances=1, coalesce=True)
    scheduler.add_job(post_todays_fixtures,      "cron", hour=7,  minute=0, id="fixtures")
    scheduler.add_job(post_football_fact,        "cron", hour=10, minute=0, id="fact")
    scheduler.add_job(post_on_this_day,          "cron", hour=8,  minute=0, id="otd")
    scheduler.add_job(_scan_injury_transfer_news, IntervalTrigger(minutes=30),                                id="news",      max_instances=1, coalesce=True)
    scheduler.add_job(refresh_analytics,         IntervalTrigger(minutes=30),                                id="analytics", max_instances=1, coalesce=True)

    logger.info("=" * 60)
    logger.info("FOOTBALL PULSE AI - Scheduler started")
    logger.info("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# Full-time results for today  (runs at midnight EAT)
# ─────────────────────────────────────────────────────────────────────────────

def post_todays_results():
    """
    Fetch all matches that finished today and post a results summary.
    Runs once at midnight EAT so it catches all day's matches.
    """
    log = setup_logger("scheduler_agent")
    log.info("Generating today's results post...")
    try:
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        today_key = f"RESULTS_{today}"

        if decision_agent.is_duplicate(today_key, "TODAYS_RESULTS"):
            log.info("Results already posted for today.")
            return

        # Fetch finished matches for today
        from agents.football_data_agent import _tracked_get, FD_BASE, normalise_match
        import time

        data = _tracked_get(
            f"{FD_BASE}/matches",
            params={"dateFrom": today, "dateTo": today, "status": "FINISHED"},
        )

        if not data:
            log.info("No results data returned.")
            return

        finished = [m for m in data.get("matches", []) if m.get("status") == "FINISHED"]

        if not finished:
            log.info("No finished matches today.")
            return

        # Build results list
        results = []
        for raw in finished:
            m = normalise_match(raw)
            results.append({
                "home_team":   m["home_team"],
                "away_team":   m["away_team"],
                "home_score":  m["home_score"],
                "away_score":  m["away_score"],
                "competition": m["competition"],
            })

        # Build caption
        lines = ["TODAY'S RESULTS\n"]
        for r in results:
            lines.append(
                f"{r['competition']}\n"
                f"{r['home_team']} {r['home_score']} - {r['away_score']} {r['away_team']}"
            )
        cap = "\n\n".join(lines)
        cap += "\n\n#Football #FootballResults #FootballPulse"

        # Create a poster using the fixtures template (reused for results)
        poster_path = poster_agent.create_todays_fixtures([
            {
                "home_team":    r["home_team"],
                "away_team":    r["away_team"],
                "kickoff_time": f"{r['home_score']}-{r['away_score']}",
                "competition":  r["competition"],
            }
            for r in results
        ])

        db_id = publisher_agent.create_post_record(None, poster_path, cap)
        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(today_key, "TODAYS_RESULTS",
                                   None, None, cap, str(poster_path))
        log.info("Results posted: %d matches.", len(results))

    except Exception as e:
        log.exception("Today's results error: %s", e)
