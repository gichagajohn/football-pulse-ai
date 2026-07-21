"""
agents/football_data_agent.py — Football Pulse AI
Collects football data from Football-Data.org, TheSportsDB, and RSS feeds.
"""

import json
import feedparser
from datetime import datetime, timezone
from typing import Optional

import settings
from utils.logger import setup_logger
from utils.http import get_json, session

logger = setup_logger("data_agent")

FD_BASE  = "https://api.football-data.org/v4"
SDB_BASE = "https://www.thesportsdb.com/api/v1/json"

# ── All competition codes we care about (football-data.org codes) ──────────
# Free tier covers: PL, PD, BL1, SA, FL1, DED, PPL, CL, EC, WC
WATCHED_COMPETITIONS = [
    "WC",   # FIFA World Cup  ← this was missing entirely
    "CL",   # UEFA Champions League
    "PL",   # Premier League
    "PD",   # La Liga
    "BL1",  # Bundesliga
    "SA",   # Serie A
    "FL1",  # Ligue 1
    "EC",   # European Championship
]


def _fd_headers() -> dict:
    return {"X-Auth-Token": settings.FOOTBALL_DATA_API_KEY}


def get_live_matches() -> list[dict]:
    """
    Return matches currently in progress.
    Queries each watched competition separately because the free tier
    /matches?status=IN_PLAY endpoint often misses tournaments like the World Cup.
    """
    all_matches = []

    # First try the global endpoint
    data = get_json(f"{FD_BASE}/matches", params={"status": "IN_PLAY"}, headers=_fd_headers())
    if data:
        all_matches.extend(data.get("matches", []))

    # Then explicitly poll each key competition so World Cup is never missed
    seen_ids = {str(m.get("id")) for m in all_matches}
    for code in WATCHED_COMPETITIONS:
        try:
            comp_data = get_json(
                f"{FD_BASE}/competitions/{code}/matches",
                params={"status": "IN_PLAY"},
                headers=_fd_headers(),
            )
            if comp_data:
                for m in comp_data.get("matches", []):
                    mid = str(m.get("id"))
                    if mid not in seen_ids:
                        all_matches.append(m)
                        seen_ids.add(mid)
        except Exception as e:
            logger.warning("Live match fetch failed for %s: %s", code, e)

    logger.info("Live matches fetched: %d", len(all_matches))
    return all_matches


def get_todays_fixtures() -> list[dict]:
    """Return today's scheduled matches across all watched competitions."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_fixtures = []
    seen_ids = set()

    # Global endpoint first
    data = get_json(
        f"{FD_BASE}/matches",
        params={"dateFrom": today, "dateTo": today},
        headers=_fd_headers(),
    )
    if data:
        for m in data.get("matches", []):
            mid = str(m.get("id"))
            if mid not in seen_ids:
                all_fixtures.append(m)
                seen_ids.add(mid)

    # Then per-competition so World Cup fixtures always appear
    for code in WATCHED_COMPETITIONS:
        try:
            comp_data = get_json(
                f"{FD_BASE}/competitions/{code}/matches",
                params={"dateFrom": today, "dateTo": today},
                headers=_fd_headers(),
            )
            if comp_data:
                for m in comp_data.get("matches", []):
                    mid = str(m.get("id"))
                    if mid not in seen_ids:
                        all_fixtures.append(m)
                        seen_ids.add(mid)
        except Exception as e:
            logger.warning("Fixture fetch failed for %s: %s", code, e)

    logger.info("Today's fixtures fetched: %d", len(all_fixtures))
    return all_fixtures


def get_standings(competition_code: str) -> Optional[dict]:
    data = get_json(
        f"{FD_BASE}/competitions/{competition_code}/standings",
        headers=_fd_headers()
    )
    return data


def get_top_scorers(competition_code: str, season: int = None) -> list[dict]:
    params = {}
    if season:
        params["season"] = season
    data = get_json(
        f"{FD_BASE}/competitions/{competition_code}/scorers",
        params=params,
        headers=_fd_headers()
    )
    if not data:
        return []
    return data.get("scorers", [])


def get_match_detail(match_id: int) -> Optional[dict]:
    return get_json(f"{FD_BASE}/matches/{match_id}", headers=_fd_headers())


def _sdb(endpoint: str, params: dict = None):
    key = settings.THESPORTSDB_API_KEY
    url = f"{SDB_BASE}/{key}/{endpoint}"
    return get_json(url, params=params)


def get_team_info(team_name: str) -> Optional[dict]:
    data = _sdb("searchteams.php", {"t": team_name})
    if data and data.get("teams"):
        return data["teams"][0]
    return None


def get_team_logo_url(team_name: str) -> Optional[str]:
    info = get_team_info(team_name)
    if info:
        return info.get("strTeamBadge")
    return None


def get_player_photo_url(player_name: str) -> Optional[str]:
    data = _sdb("searchplayers.php", {"p": player_name})
    if data and data.get("player"):
        return data["player"][0].get("strThumb") or data["player"][0].get("strCutout")
    return None


def get_last_5_matches(team_id: str) -> list[dict]:
    data = _sdb(f"eventslast5.php?id={team_id}")
    if not data:
        return []
    return data.get("results", [])


def get_next_5_matches(team_id: str) -> list[dict]:
    data = _sdb(f"eventsnext5.php?id={team_id}")
    if not data:
        return []
    return data.get("events", [])


def get_historical_fact_by_date(month: int, day: int) -> list[dict]:
    data = _sdb(f"eventsonthisday.php?month={month}&day={day}&l=Soccer")
    if not data:
        return []
    return data.get("events", [])


def fetch_rss_news(max_items: int = 10) -> list[dict]:
    articles = []
    for url in settings.RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                articles.append({
                    "title":     entry.get("title", ""),
                    "summary":   entry.get("summary", ""),
                    "link":      entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source":    feed.feed.get("title", url),
                })
        except Exception as e:
            logger.warning("RSS fetch failed for %s: %s", url, e)
    logger.info("RSS articles fetched: %d", len(articles))
    return articles


def normalise_match(raw: dict) -> dict:
    competition = raw.get("competition", {})
    home = raw.get("homeTeam", {})
    away = raw.get("awayTeam", {})
    score = raw.get("score", {})
    full = score.get("fullTime", {})
    half = score.get("halfTime", {})

    return {
        "match_id":    str(raw.get("id", "")),
        "competition": competition.get("name", "Unknown"),
        "home_team":   home.get("name", "Home"),
        "away_team":   away.get("name", "Away"),
        "home_score":  full.get("home") or half.get("home") or 0,
        "away_score":  full.get("away") or half.get("away") or 0,
        "status":      raw.get("status", ""),
        "minute":      raw.get("minute"),
        "utc_date":    raw.get("utcDate", ""),
        "venue":       raw.get("venue", ""),
        "referees":    raw.get("referees", []),
        "raw":         json.dumps(raw),
    }


def normalise_scorer(raw: dict) -> dict:
    player = raw.get("player", {})
    team   = raw.get("team", {})
    return {
        "player_name": player.get("name", "Unknown"),
        "team":        team.get("name", "Unknown"),
        "goals":       raw.get("goals", 0),
        "assists":     raw.get("assists", 0),
        "penalties":   raw.get("penalties", 0),
    }
