"""
agents/scheduler_agent.py — Football Pulse AI
Orchestrates all recurring jobs using APScheduler.
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

from agents import football_data_agent  as data_agent
from agents import content_decision_agent as decision_agent
from agents import poster_design_agent   as poster_agent
from agents import caption_agent
from agents import publisher_agent
from agents import analytics_agent

logger = setup_logger("scheduler")

TZ = pytz.timezone(settings.TIMEZONE)

_previous_scores: dict = {}


def check_live_matches():
    logger.debug("Checking live matches...")
    try:
        matches = data_agent.get_live_matches()
    except Exception as e:
        logger.warning("Live match fetch failed: %s", e)
        return

    for raw in matches:
        match = data_agent.normalise_match(raw)
        mid   = match["match_id"]
        home  = match["home_score"]
        away  = match["away_score"]
        status= match["status"]
        comp  = match["competition"]

        prev = _previous_scores.get(mid)

        if prev and (home > prev[0] or away > prev[1]):
            scoring_team = match["home_team"] if home > prev[0] else match["away_team"]
            _handle_goal(match, scoring_team)

        if prev and prev[2] != "FINISHED" and status == "FINISHED":
            _handle_fulltime(match)

        _previous_scores[mid] = (home, away, status)


def _handle_goal(match: dict, scoring_team: str):
    mid   = match["match_id"]
    comp  = match["competition"]
    home  = match["home_score"]
    away  = match["away_score"]
    minute = match.get("minute") or 0

    scorer = scoring_team
    event_id = f"GOAL_{mid}_{home}_{away}"

    if decision_agent.is_duplicate(mid, "GOAL", minute, scorer):
        return

    should, priority = decision_agent.should_post("GOAL", comp)
    if not should:
        return

    if not decision_agent.within_rate_limit():
        return

    try:
        poster_path = poster_agent.create_goal_alert(
            home_team  = match["home_team"],
            away_team  = match["away_team"],
            home_score = home,
            away_score = away,
            scorer     = scorer,
            minute     = minute,
            competition= comp,
        )

        cap = caption_agent.generate_goal_caption(
            scorer     = scorer,
            team       = scoring_team,
            home_team  = match["home_team"],
            away_team  = match["away_team"],
            home_score = home,
            away_score = away,
            minute     = minute,
            competition= comp,
        )

        db_id = publisher_agent.create_post_record(
            event_id=decision_agent.store_event(
                event_id=event_id, event_type="GOAL",
                competition=comp, home_team=match["home_team"],
                away_team=match["away_team"], home_score=home,
                away_score=away, minute=minute,
                match_id=mid, priority=priority,
            ) or None,
            poster_path=poster_path,
            caption_text=cap,
        )

        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(mid, "GOAL", minute, scorer, cap, str(poster_path))

    except Exception as e:
        logger.exception("Goal handling error: %s", e)


def _handle_fulltime(match: dict):
    mid  = match["match_id"]
    comp = match["competition"]

    if decision_agent.is_duplicate(mid, "FULLTIME"):
        return

    should, priority = decision_agent.should_post("FULLTIME", comp)
    if not should:
        return

    if not decision_agent.within_rate_limit():
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

        db_id = publisher_agent.create_post_record(
            event_id=None, poster_path=poster_path, caption_text=cap,
        )
        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(mid, "FULLTIME", None, None, cap, str(poster_path))

    except Exception as e:
        logger.exception("Full-time handling error: %s", e)


_COMPETITIONS = ["PL", "PD", "BL1", "SA", "FL1", "WC", "CL"]
_comp_idx = 0

def update_standings():
    global _comp_idx
    comp_code = _COMPETITIONS[_comp_idx % len(_COMPETITIONS)]
    _comp_idx += 1

    logger.debug("Fetching standings for %s", comp_code)
    try:
        data = data_agent.get_standings(comp_code)
        if not data:
            return

        standings_raw = data.get("standings", [])
        if not standings_raw:
            return

        table_raw  = standings_raw[0].get("table", [])
        comp_name  = data.get("competition", {}).get("name", comp_code)
        season     = str(data.get("season", {}).get("startDate", "")[:4])

        standings = [
            {
                "position": r.get("position"),
                "team":     r.get("team", {}).get("name", ""),
                "played":   r.get("playedGames", 0),
                "won":      r.get("won", 0),
                "drawn":    r.get("draw", 0),
                "lost":     r.get("lost", 0),
                "gd":       r.get("goalDifference", 0),
                "points":   r.get("points", 0),
            }
            for r in table_raw
        ]

        if decision_agent.is_duplicate(comp_code, "LEAGUE_TABLE"):
            return

        poster_path = poster_agent.create_league_table(comp_name, standings, season)
        leader = standings[0]["team"] if standings else "Unknown"
        pts    = standings[0]["points"] if standings else 0
        cap    = caption_agent.generate_league_table_caption(comp_name, leader, pts)

        db_id = publisher_agent.create_post_record(None, poster_path, cap)
        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(comp_code, "LEAGUE_TABLE", None, None, cap, str(poster_path))

    except Exception as e:
        logger.exception("Standings update error: %s", e)


def post_todays_fixtures():
    logger.info("Generating today's fixtures post...")
    try:
        # Only post fixtures once per day
        today_key = datetime.now().strftime("%Y%m%d")
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
            dt = raw.get("utcDate", "")
            try:
                from datetime import datetime as dt_cls
                kickoff = dt_cls.fromisoformat(dt.replace("Z", "+00:00"))
                kickoff_local = kickoff.astimezone(TZ).strftime("%H:%M")
            except Exception:
                kickoff_local = "TBC"
            fixtures.append({
                "home_team":    m["home_team"],
                "away_team":    m["away_team"],
                "kickoff_time": kickoff_local,
                "competition":  m["competition"],
            })

        poster_path = poster_agent.create_todays_fixtures(fixtures)
        cap = f"TODAY'S FOOTBALL FIXTURES\n\nHere's what's on today!\n\n#Football #TodaysFixtures #FootballPulse"

        db_id = publisher_agent.create_post_record(None, poster_path, cap)
        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(today_key, "TODAYS_FIXTURES", None, None, cap, str(poster_path))

    except Exception as e:
        logger.exception("Today's fixtures error: %s", e)


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
    "Portugal's Eusebio scored 9 goals at the 1966 World Cup - a record that stood for decades.",
    "The first penalty kick in World Cup history was scored in 1930.",
    "Kevin De Bruyne is considered one of the greatest playmakers in Premier League history.",
    "Vinicius Jr won the Ballon d'Or in 2024, becoming Brazil's first winner since Ronaldo in 1997.",
    "The 2022 World Cup in Qatar was the first held in the Middle East.",
    "Japan beat Germany and Spain at the 2022 World Cup in one of football's biggest upsets.",
    "Morocco became the first African nation to reach the World Cup semi-finals in 2022.",
    "Didier Drogba is Ivory Coast's greatest ever footballer and a Chelsea legend.",
    "Liverpool's incredible comeback from 3-0 down to beat AC Milan in the 2005 Champions League final is known as the Miracle of Istanbul.",
]


def post_football_fact():
    logger.debug("Generating football fact post...")
    try:
        # Pick a random fact that hasn't been posted recently
        random.shuffle(FOOTBALL_FACTS)
        for fact in FOOTBALL_FACTS:
            fact_key = f"FACT_{hash(fact) % 999999}"
            if not decision_agent.is_duplicate(fact_key, "FOOTBALL_FACT"):
                poster_path = poster_agent.create_football_fact(fact)
                cap = caption_agent.generate_fact_caption(fact)
                db_id = publisher_agent.create_post_record(None, poster_path, cap)
                publisher_agent.publish(poster_path, cap, post_id_db=db_id)
                decision_agent.record_post(fact_key, "FOOTBALL_FACT", None, None, cap, str(poster_path))
                logger.info("Football fact posted successfully.")
                return
        logger.info("All facts recently posted, skipping.")

    except Exception as e:
        logger.exception("Football fact error: %s", e)


def post_on_this_day():
    logger.debug("Generating On This Day post...")
    try:
        now = datetime.now()
        events = data_agent.get_historical_fact_by_date(now.month, now.day)
        if not events:
            return

        event = random.choice(events)
        name    = event.get("strEvent", "")
        season  = event.get("strSeason", "")
        result  = event.get("intHomeScore", "?")
        if not name:
            return

        fact = f"On this day in {season}: {name} - {result}"
        key  = f"OTD_{now.strftime('%m%d')}_{hash(name) % 9999}"

        if decision_agent.is_duplicate(key, "ON_THIS_DAY"):
            return

        poster_path = poster_agent.create_football_fact(fact, category="ON THIS DAY", emoji="")
        cap = f"ON THIS DAY IN FOOTBALL\n\n{fact}\n\n#OnThisDay #FootballHistory #FootballPulse"

        db_id = publisher_agent.create_post_record(None, poster_path, cap)
        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        decision_agent.record_post(key, "ON_THIS_DAY", None, None, cap, str(poster_path))

    except Exception as e:
        logger.exception("On This Day error: %s", e)


def refresh_analytics():
    logger.debug("Refreshing engagement analytics...")
    try:
        analytics_agent.update_all_engagement()
        analytics_agent.log_summary()
    except Exception as e:
        logger.warning("Analytics refresh error: %s", e)


def start():
    from database.schema import init_db
    init_db()

    scheduler = BlockingScheduler(timezone=TZ)

    scheduler.add_job(check_live_matches, IntervalTrigger(seconds=settings.LIVE_CHECK_INTERVAL), id="live_matches", max_instances=1, coalesce=True)
    scheduler.add_job(update_standings, IntervalTrigger(seconds=settings.STANDINGS_CHECK_INTERVAL), id="standings", max_instances=1, coalesce=True)
    scheduler.add_job(post_todays_fixtures, "cron", hour=7, minute=0, id="fixtures")
    scheduler.add_job(post_football_fact, IntervalTrigger(seconds=settings.FACTS_INTERVAL), id="facts", max_instances=1, coalesce=True)
    scheduler.add_job(post_on_this_day, IntervalTrigger(seconds=settings.HISTORICAL_INTERVAL), id="on_this_day", max_instances=1, coalesce=True)
    scheduler.add_job(refresh_analytics, IntervalTrigger(minutes=30), id="analytics", max_instances=1, coalesce=True)
    scheduler.add_job(_scan_injury_transfer_news, IntervalTrigger(minutes=30), id="news_scan", max_instances=1, coalesce=True)

    logger.info("=" * 60)
    logger.info("FOOTBALL PULSE AI - Scheduler started")
    logger.info("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


def _scan_injury_transfer_news():
    from agents.injury_transfer_agent import scan_for_news
    try:
        scan_for_news()
    except Exception as e:
        logger.warning("Injury/transfer scan error: %s", e)