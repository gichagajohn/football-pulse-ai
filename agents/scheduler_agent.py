"""
agents/scheduler_agent.py — Football Pulse AI
Orchestrates all recurring jobs.
Match state is persisted in the match_state DB table so goal/fulltime
detection works correctly across GitHub Actions runs.
"""

import random
import hashlib
from datetime import datetime, timezone

from utils.logger import setup_logger
from database.schema import get_connection, init_db

log = setup_logger("scheduler_agent")


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
# Live match handling
# ─────────────────────────────────────────────────────────────────────────────

def _handle_goal(match: dict, home_score: int, away_score: int) -> None:
    try:
        from agents import poster_design_agent as poster
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

        poster_path = poster.create_goal_alert(
            home_team=home, away_team=away,
            home_score=home_score, away_score=away_score,
            scorer="", minute=minute, competition=competition,
        )
        # Correct signature: scorer, team, home_team, away_team, home_score, away_score, minute, competition
        cap = caption_agent.generate_goal_caption(
            scorer="", team=home,
            home_team=home, away_team=away,
            home_score=home_score, away_score=away_score,
            minute=minute, competition=competition,
        )
        db_id = publisher_agent.create_post_record(0, poster_path, cap)
        fb_id = publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        record_post("GOAL", key, competition, fb_id)
        log.info("Goal posted: %s %d-%d", mid, home_score, away_score)

    except Exception as e:
        log.error("_handle_goal error: %s", e)


def _handle_fulltime(match: dict, home_score: int, away_score: int) -> None:
    try:
        from agents import poster_design_agent as poster
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

        poster_path = poster.create_fulltime(
            home_team=home, away_team=away,
            home_score=home_score, away_score=away_score,
            competition=competition,
        )
        # Correct signature: home_team, away_team, home_score, away_score, competition, goals=None
        cap = caption_agent.generate_fulltime_caption(
            home_team=home, away_team=away,
            home_score=home_score, away_score=away_score,
            competition=competition,
        )
        db_id = publisher_agent.create_post_record(0, poster_path, cap)
        fb_id = publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        record_post("FULLTIME", key, competition, fb_id)
        log.info("Full-time posted: %s %d-%d", mid, home_score, away_score)

    except Exception as e:
        log.error("_handle_fulltime error: %s", e)


def check_live_matches() -> None:
    try:
        from agents.football_data_agent import get_live_matches
        matches = get_live_matches()
        log.info("Live matches fetched: %d", len(matches))
    except Exception as e:
        log.error("check_live_matches fetch error: %s", e)
        return

    for match in matches:
        try:
            mid        = str(match.get("id", ""))
            ft         = match.get("score", {}).get("fullTime", {})
            home_score = ft.get("home") or 0
            away_score = ft.get("away") or 0
            status     = match.get("status", "")

            prev = _get_prev_state(mid)

            if prev is None:
                log.info("New match baseline: %s (status=%s %d-%d)", mid, status, home_score, away_score)
                _save_state(mid, home_score, away_score, status)
                continue

            if home_score + away_score > prev["home"] + prev["away"]:
                log.info("Goal detected: %s %d-%d (was %d-%d)", mid, home_score, away_score, prev["home"], prev["away"])
                _handle_goal(match, home_score, away_score)

            if status in ("FINISHED", "FT") and prev["status"] not in ("FINISHED", "FT"):
                log.info("Full-time detected: %s %d-%d", mid, home_score, away_score)
                _handle_fulltime(match, home_score, away_score)

            _save_state(mid, home_score, away_score, status)

        except Exception as e:
            log.error("Match loop error %s: %s", match.get("id", "?"), e)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def post_todays_fixtures() -> None:
    try:
        from agents.football_data_agent import get_todays_fixtures
        from agents import poster_design_agent as poster
        from agents import caption_agent
        from agents import publisher_agent
        from agents.content_decision_agent import should_post, record_post, is_duplicate

        fixtures = get_todays_fixtures()
        if not fixtures:
            log.info("No fixtures today.")
            return

        today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dedup_key = f"fixtures:{today}"

        if is_duplicate("FIXTURE_POST", dedup_key):
            log.info("Fixtures already posted today.")
            return

        if not should_post("FIXTURE_POST", "default", dedup_key=dedup_key):
            return

        fixture_list = [
            {
                "home_team":    f.get("homeTeam", {}).get("name", ""),
                "away_team":    f.get("awayTeam", {}).get("name", ""),
                "kickoff_time": f.get("utcDate", "TBC")[:16].replace("T", " "),
                "competition":  f.get("competition", {}).get("name", ""),
            }
            for f in fixtures[:10]
        ]

        poster_path = poster.create_todays_fixtures(fixture_list)

        # Build caption manually — generate_fixtures_caption doesn't exist in caption_agent
        lines = ["📅 TODAY'S FIXTURES\n"]
        for fix in fixture_list:
            lines.append(f"{fix['home_team']} vs {fix['away_team']} | {fix['kickoff_time']}")
        lines.append("\nWho are you watching today? 👇")
        lines.append("\n#Football #FootballPulse #Fixtures #Soccer")
        cap = "\n".join(lines)

        db_id = publisher_agent.create_post_record(0, poster_path, cap)
        fb_id = publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        record_post("FIXTURE_POST", dedup_key, "default", fb_id)
        log.info("Fixtures posted: %d matches", len(fixture_list))

    except Exception as e:
        log.error("post_todays_fixtures: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Football fact
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
]


def post_football_fact() -> None:
    try:
        from agents import poster_design_agent as poster
        from agents import caption_agent
        from agents import publisher_agent
        from agents.content_decision_agent import should_post, record_post, is_duplicate

        # Pick a fact not recently posted
        chosen_fact = None
        chosen_key  = None
        for fact in random.sample(FOOTBALL_FACTS, len(FOOTBALL_FACTS)):
            key = hashlib.md5(fact.encode()).hexdigest()[:12]
            if not is_duplicate("FOOTBALL_FACT", key):
                chosen_fact = fact
                chosen_key  = key
                break

        if not chosen_fact:
            chosen_fact = random.choice(FOOTBALL_FACTS)
            chosen_key  = hashlib.md5(chosen_fact.encode()).hexdigest()[:12]

        if not should_post("FOOTBALL_FACT", "default", dedup_key=chosen_key):
            return

        poster_path = poster.create_football_fact(chosen_fact, category="DID YOU KNOW?", emoji="🧠")
        # generate_fact_caption exists in caption_agent
        cap = caption_agent.generate_fact_caption(chosen_fact)
        db_id = publisher_agent.create_post_record(0, poster_path, cap)
        fb_id = publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        record_post("FOOTBALL_FACT", chosen_key, "default", fb_id)
        log.info("Fact posted.")

    except Exception as e:
        log.error("post_football_fact: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# On This Day
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
]


def post_on_this_day() -> None:
    try:
        from agents import poster_design_agent as poster
        from agents import caption_agent
        from agents import publisher_agent
        from agents.content_decision_agent import should_post, record_post, is_duplicate

        today        = datetime.now(timezone.utc).strftime("%m-%d")
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

        poster_path = poster.create_football_fact(event["text"], category="ON THIS DAY", emoji="📅")
        cap = caption_agent.generate_fact_caption(f"On This Day: {event['text']}")
        db_id = publisher_agent.create_post_record(0, poster_path, cap)
        fb_id = publisher_agent.publish(poster_path, cap, post_id_db=db_id)
        record_post("ON_THIS_DAY", key, "default", fb_id)
        log.info("OTD posted: %s", today)

    except Exception as e:
        log.error("post_on_this_day: %s", e)