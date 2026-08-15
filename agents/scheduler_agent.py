"""
agents/scheduler_agent.py — Football Pulse AI
Orchestrates all recurring jobs. Text-only posts — no poster generation.
Match state is persisted in the match_state DB table so goal/fulltime
detection works correctly across GitHub Actions runs.
"""

import random
import hashlib
from datetime import datetime, timezone, timedelta

from utils.logger import setup_logger
from database.schema import get_connection, init_db

log = setup_logger("scheduler_agent")

EAT = timezone(timedelta(hours=3))


# ─────────────────────────────────────────────────────────────────────────────
# Match state persistence
# ─────────────────────────────────────────────────────────────────────────────

def _get_prev_state(match_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT home_score, away_score, status FROM match_state WHERE match_id = ?",
            (match_id,),
        ).fetchone()
    if row is None:
        return None
    return {"home": row["home_score"], "away": row["away_score"], "status": row["status"]}


def _save_state(match_id: str, home: int, away: int, status: str) -> None:
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


# ─────────────────────────────────────────────────────────────────────────────
# Live match handling — text-only
# ─────────────────────────────────────────────────────────────────────────────

def _handle_goal(match: dict, home_score: int, away_score: int) -> None:
    try:
        from agents import caption_agent
        from agents import publisher_agent
        from agents.content_decision_agent import should_post, record_post

        competition = match.get("competition", {}).get("name", "default")
        mid  = str(match.get("id", ""))
        key  = f"{mid}:{home_score}:{away_score}"

        if not should_post("GOAL", competition, dedup_key=key):
            return

        home   = match.get("homeTeam", {}).get("name", "Home")
        away   = match.get("awayTeam", {}).get("name", "Away")
        minute = match.get("minute", 90)

        cap = caption_agent.generate_goal_caption(
            scorer="", team=home,
            home_team=home, away_team=away,
            home_score=home_score, away_score=away_score,
            minute=minute, competition=competition,
        )
        db_id = publisher_agent.create_post_record(0, "", cap)
        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
        record_post("GOAL", key, competition, fb_id)
        log.info("Goal posted: %s %d-%d (%s)", mid, home_score, away_score, competition)

    except Exception as e:
        log.error("_handle_goal error: %s", e)


def _handle_fulltime(match: dict, home_score: int, away_score: int) -> None:
    try:
        from agents import caption_agent
        from agents import publisher_agent
        from agents.content_decision_agent import should_post, record_post

        competition = match.get("competition", {}).get("name", "default")
        mid  = str(match.get("id", ""))
        key  = f"FT:{mid}"

        if not should_post("FULLTIME", competition, dedup_key=key):
            return

        home = match.get("homeTeam", {}).get("name", "Home")
        away = match.get("awayTeam", {}).get("name", "Away")

        cap = caption_agent.generate_fulltime_caption(
            home_team=home, away_team=away,
            home_score=home_score, away_score=away_score,
            competition=competition,
        )
        db_id = publisher_agent.create_post_record(0, "", cap)
        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
        record_post("FULLTIME", key, competition, fb_id)
        log.info("Full-time posted: %s %d-%d (%s)", mid, home_score, away_score, competition)

    except Exception as e:
        log.error("_handle_fulltime error: %s", e)


def check_live_matches() -> None:
    try:
        from agents.football_data_agent import get_live_matches
        matches = get_live_matches()
        log.info("Live matches to process: %d", len(matches))
    except Exception as e:
        log.error("check_live_matches fetch error: %s", e)
        return

    for match in matches:
        try:
            mid        = str(match.get("id", ""))
            score      = match.get("score", {})
            ft         = score.get("fullTime", {})
            ht         = score.get("halfTime", {})
            home_score = ft.get("home") or ht.get("home") or 0
            away_score = ft.get("away") or ht.get("away") or 0
            status     = match.get("status", "")
            competition = match.get("competition", {}).get("name", "Unknown")

            prev = _get_prev_state(mid)

            if prev is None:
                log.info("New match baseline: %s [%s] %s %d-%d",
                         mid, competition, status, home_score, away_score)
                _save_state(mid, home_score, away_score, status)
                continue

            if home_score + away_score > prev["home"] + prev["away"]:
                log.info("GOAL detected [%s]: %s %d-%d (was %d-%d)",
                         competition, mid, home_score, away_score, prev["home"], prev["away"])
                _handle_goal(match, home_score, away_score)

            if status in ("FINISHED", "FT") and prev["status"] not in ("FINISHED", "FT"):
                log.info("FULL TIME [%s]: %s %d-%d", competition, mid, home_score, away_score)
                _handle_fulltime(match, home_score, away_score)

            _save_state(mid, home_score, away_score, status)

        except Exception as e:
            log.error("Match loop error %s: %s", match.get("id", "?"), e)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — text-only
# ─────────────────────────────────────────────────────────────────────────────

def _format_kickoff_eat(utc_date_str: str) -> str:
    """Convert an ISO8601 UTC kickoff time to HH:MM EAT (UTC+3)."""
    if not utc_date_str or utc_date_str == "TBC":
        return "TBC"
    try:
        dt = datetime.fromisoformat(utc_date_str.replace("Z", "+00:00"))
        eat = dt.astimezone(EAT)
        return eat.strftime("%H:%M EAT")
    except Exception:
        return utc_date_str[:16].replace("T", " ") + " UTC"


def post_todays_fixtures() -> None:
    try:
        from agents.football_data_agent import get_todays_fixtures
        from agents import caption_agent
        from agents import publisher_agent
        from agents.content_decision_agent import should_post, record_post, is_duplicate

        fixtures = get_todays_fixtures()
        if not fixtures:
            log.info("No fixtures today.")
            return

        today     = datetime.now(EAT).strftime("%Y-%m-%d")
        dedup_key = f"fixtures:{today}"

        if is_duplicate("FIXTURE_POST", dedup_key):
            log.info("Fixtures already posted today.")
            return

        if not should_post("FIXTURE_POST", "default", dedup_key=dedup_key):
            return

        # Group by competition so the post is readable
        by_comp: dict[str, list] = {}
        for f in fixtures[:15]:
            comp = f.get("competition", {}).get("name", "Football")
            home = f.get("homeTeam", {}).get("name", "")
            away = f.get("awayTeam", {}).get("name", "")
            kt   = _format_kickoff_eat(f.get("utcDate", "TBC"))
            by_comp.setdefault(comp, []).append(f"{home} vs {away}  |  {kt}")

        lines = [f"MATCHDAY - {today}\n"]
        for comp, games in by_comp.items():
            lines.append(f"-- {comp.upper()} --")
            lines.extend(games)
            lines.append("")

        lines.append("Who are you watching today? Drop your score predictions below!")
        lines.append("\n#Football #FootballPulse #Fixtures #Soccer #WorldCup2026")
        cap = "\n".join(lines).strip()

        db_id = publisher_agent.create_post_record(0, "", cap)
        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
        record_post("FIXTURE_POST", dedup_key, "default", fb_id)
        log.info("Fixtures posted: %d matches across %d competitions",
                 len(fixtures), len(by_comp))

    except Exception as e:
        log.error("post_todays_fixtures: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Football fact — text-only, once per day
# ─────────────────────────────────────────────────────────────────────────────

FOOTBALL_FACTS = [
    "Pelé scored 1,281 goals in 1,363 games during his career.",
    "The first FIFA World Cup was held in Uruguay in 1930.",
    "Cristiano Ronaldo is the all-time top scorer in the UEFA Champions League.",
    "Lionel Messi has won the Ballon d'Or award 8 times.",
    "The fastest red card in football history was given after just 2 seconds.",
    "Brazil has won the FIFA World Cup a record 5 times.",
    "The longest penalty shootout in history lasted 48 penalties.",
    "Goalkeeper René Higuita invented the scorpion kick save.",
    "The football used in the first World Cup final was different for each half — each team brought their own.",
    "Real Madrid has won the UEFA Champions League a record 15 times.",
    "The highest scoring international match was Australia 31-0 American Samoa in 2001.",
    "Rogerio Ceni, a goalkeeper, scored 131 goals in his career.",
    "The first football club in the world is Sheffield FC, founded in 1857.",
    "Zinedine Zidane won the World Cup, Champions League, and Ballon d'Or.",
    "Paolo Maldini played his entire 25-year career at AC Milan.",
    "The 2026 FIFA World Cup is the first to be hosted by three nations — USA, Canada, and Mexico.",
    "The 2026 World Cup expanded to 48 teams for the first time in tournament history.",
    "Argentina are the reigning World Cup champions after winning the 2022 tournament in Qatar.",
    "Morocco became the first African nation to reach a World Cup semi-final, at Qatar 2022.",
    "Kylian Mbappé became only the second player after Pelé to score in two World Cup finals.",
]


def post_football_fact() -> None:
    try:
        from agents import caption_agent
        from agents import publisher_agent
        from agents.content_decision_agent import should_post, record_post, is_duplicate

        today   = datetime.now(EAT).strftime("%Y-%m-%d")
        day_key = f"fact:{today}"

        if is_duplicate("FOOTBALL_FACT", day_key):
            log.info("Football fact already posted today.")
            return

        if not should_post("FOOTBALL_FACT", "default", dedup_key=day_key):
            return

        chosen_fact = random.choice(FOOTBALL_FACTS)

        cap = caption_agent.generate_fact_caption(chosen_fact)
        db_id = publisher_agent.create_post_record(0, "", cap)
        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
        record_post("FOOTBALL_FACT", day_key, "default", fb_id)
        log.info("Fact posted: %s", chosen_fact[:50])

    except Exception as e:
        log.error("post_football_fact: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# On This Day — text-only
# ─────────────────────────────────────────────────────────────────────────────

ON_THIS_DAY_EVENTS = [
    {"date": "06-14", "text": "In 1994, the FIFA World Cup opened in the USA with a stunning ceremony."},
    {"date": "05-25", "text": "In 2005, Liverpool completed the miracle of Istanbul — 3-0 down at half time, they won the Champions League on penalties against AC Milan."},
    {"date": "07-09", "text": "In 2006, Zinedine Zidane headbutted Marco Materazzi in his last-ever match — the World Cup final."},
    {"date": "06-08", "text": "In 2010, the FIFA World Cup kicked off in South Africa for the first time on African soil."},
    {"date": "07-13", "text": "In 2014, Germany beat Argentina 1-0 in extra time to win the World Cup in Brazil."},
    {"date": "05-29", "text": "In 1985, the Heysel Stadium disaster claimed 39 lives before the European Cup final."},
    {"date": "04-15", "text": "In 1989, the Hillsborough disaster resulted in 97 Liverpool supporters losing their lives."},
    {"date": "05-26", "text": "In 1999, Manchester United won the treble with a dramatic injury-time comeback against Bayern Munich."},
    {"date": "07-15", "text": "In 2018, France won the FIFA World Cup in Russia, beating Croatia 4-2 in the final."},
    {"date": "07-18", "text": "In 2026, Argentina face their first World Cup knockout match as defending champions."},
]


def post_on_this_day() -> None:
    try:
        from agents import caption_agent
        from agents import publisher_agent
        from agents.content_decision_agent import should_post, record_post, is_duplicate

        today        = datetime.now(EAT).strftime("%m-%d")
        events_today = [e for e in ON_THIS_DAY_EVENTS if e["date"] == today]

        if not events_today:
            log.info("No On This Day event for %s", today)
            return

        event = events_today[0]
        key   = f"otd:{today}"

        if is_duplicate("ON_THIS_DAY", key):
            log.info("OTD already posted today.")
            return

        if not should_post("ON_THIS_DAY", "default", dedup_key=key):
            return

        cap = caption_agent.generate_fact_caption(f"On This Day: {event['text']}")
        db_id = publisher_agent.create_post_record(0, "", cap)
        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
        record_post("ON_THIS_DAY", key, "default", fb_id)
        log.info("OTD posted: %s", today)

    except Exception as e:
        log.error("post_on_this_day: %s", e)
