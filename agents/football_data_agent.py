"""
agents/football_data_agent.py — Football Pulse AI
Collects football data from Football-Data.org, TheSportsDB, and RSS feeds.
All sources are free. No paid API required.
"""

import json
import feedparser
from datetime import datetime, timezone
from typing import Optional

import settings
from utils.logger import setup_logger
from utils.http import get_json, session

logger = setup_logger("data_agent")

# ── API base URLs ──────────────────────────────────────────────────────────
FD_BASE  = "https://api.football-data.org/v4"     # football-data.org
SDB_BASE = "https://www.thesportsdb.com/api/v1/json"


# ─────────────────────────────────────────────────────────────────────────────
# Football-Data.org helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fd_headers() -> dict:
    return {"X-Auth-Token": settings.FOOTBALL_DATA_API_KEY}


def get_live_matches() -> list[dict]:
    """Return matches currently in progress from football-data.org."""
    data = get_json(f"{FD_BASE}/matches", params={"status": "LIVE"}, headers=_fd_headers())
    if not data:
        return []
    matches = data.get("matches", [])
    logger.info("Live matches fetched: %d", len(matches))
    return matches


def get_todays_fixtures() -> list[dict]:
    """Return today's scheduled matches."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data = get_json(
        f"{FD_BASE}/matches",
        params={"dateFrom": today, "dateTo": today},
        headers=_fd_headers()
    )
    if not data:
        return []
    return data.get("matches", [])


def get_standings(competition_code: str) -> Optional[dict]:
    """
    Fetch league table for a competition.
    competition_code examples: PL, PD, BL1, SA, FL1, CL, WC
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# TheSportsDB helpers  (free key = "1")
# ─────────────────────────────────────────────────────────────────────────────

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
    """On-this-day style facts from TheSportsDB."""
    data = _sdb(f"eventsonthisday.php?month={month}&day={day}&l=Soccer")
    if not data:
        return []
    return data.get("events", [])


# ─────────────────────────────────────────────────────────────────────────────
# RSS Feed parser
# ─────────────────────────────────────────────────────────────────────────────

def fetch_rss_news(max_items: int = 10) -> list[dict]:
    """Pull latest headlines from all configured RSS feeds."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Event Normalisation
# Converts raw API payloads into a standard internal dict
# ─────────────────────────────────────────────────────────────────────────────

def normalise_match(raw: dict) -> dict:
    """Flatten a football-data.org match dict into our standard schema."""
    competition = raw.get("competition", {})
    home = raw.get("homeTeam", {})
    away = raw.get("awayTeam", {})
    score = raw.get("score", {})
    full = score.get("fullTime", {})
    half = score.get("halfTime", {})

    return {
        "match_id":       str(raw.get("id", "")),
        "competition":    competition.get("name", "Unknown"),
        "home_team":      home.get("name", "Home"),
        "away_team":      away.get("name", "Away"),
        "home_score":     full.get("home") or half.get("home") or 0,
        "away_score":     full.get("away") or half.get("away") or 0,
        "status":         raw.get("status", ""),
        "minute":         raw.get("minute"),
        "utc_date":       raw.get("utcDate", ""),
        "venue":          raw.get("venue", ""),
        "referees":       raw.get("referees", []),
        "raw":            json.dumps(raw),
    }


def normalise_scorer(raw: dict) -> dict:
    player = raw.get("player", {})
    team   = raw.get("team", {})
    return {
        "player_name":  player.get("name", "Unknown"),
        "team":         team.get("name", "Unknown"),
        "goals":        raw.get("goals", 0),
        "assists":      raw.get("assists", 0),
        "penalties":    raw.get("penalties", 0),
    }
