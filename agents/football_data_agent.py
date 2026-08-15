"""
agents/football_data_agent.py — Football Pulse AI
Collects football data from Football-Data.org, TheSportsDB, and RSS feeds.
"""

import time
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

# All competitions on the free tier — used for fixture fetching
WATCHED_COMPETITIONS = ["WC", "CL", "PL", "PD", "BL1", "SA", "FL1", "EC", "ELC", "DED", "PPL", "BSA"]

# Simple in-process rate limiter: max 9 calls/minute (safe under the 10/min limit)
_call_timestamps: list[float] = []
_RATE_LIMIT     = 9
_RATE_WINDOW    = 60.0


def _fd_headers() -> dict:
    return {"X-Auth-Token": settings.FOOTBALL_DATA_API_KEY}


def _can_call_api() -> bool:
    now = time.time()
    while _call_timestamps and now - _call_timestamps[0] > _RATE_WINDOW:
        _call_timestamps.pop(0)
    if len(_call_timestamps) >= _RATE_LIMIT:
        logger.warning(
            "Rate limit guard: %d calls made in last 60 s — skipping API call",
            len(_call_timestamps),
        )
        return False
    return True


def _tracked_get(url: str, params: dict = None) -> Optional[dict]:
    if not _can_call_api():
        return None
    _call_timestamps.append(time.time())
    return get_json(url, params=params, headers=_fd_headers())


def get_live_matches() -> list[dict]:
    """
    Return matches currently in progress.
    Uses one global call first, then WC fallback if nothing found.
    """
    all_matches = []

    data = _tracked_get(f"{FD_BASE}/matches", params={"status": "IN_PLAY"})
    if data:
        all_matches.extend(data.get("matches", []))

    logger.info("Live matches fetched: %d", len(all_matches))

    if not all_matches and _can_call_api():
        time.sleep(7)
        wc_data = _tracked_get(
            f"{FD_BASE}/competitions/WC/matches",
            params={"status": "IN_PLAY"},
        )
        if wc_data:
            all_matches.extend(wc_data.get("matches", []))
            logger.info("WC live matches fetched: %d", len(all_matches))

    return all_matches


def get_todays_fixtures() -> list[dict]:
    """
    Return today's scheduled matches by querying each competition individually.

    The global /matches endpoint misses competitions sometimes, so we query
    each competition separately with a short delay between calls to stay
    within the 10 req/min rate limit.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_fixtures = []
    seen_ids: set[str] = set()

    # Step 1: Try the global call first (free, fast)
    data = _tracked_get(
        f"{FD_BASE}/matches",
        params={"dateFrom": today, "dateTo": today},
    )
    if data:
        for m in data.get("matches", []):
            mid = str(m.get("id", ""))
            if mid not in seen_ids:
                all_fixtures.append(m)
                seen_ids.add(mid)

    logger.info("Global fixtures fetched: %d", len(all_fixtures))

    # Step 2: Query each competition individually to catch any missed ones
    # Use a 7-second delay between calls to stay under rate limit
    for comp_code in WATCHED_COMPETITIONS:
        if not _can_call_api():
            logger.warning("Rate limit reached during fixture fetch — stopping at %d fixtures", len(all_fixtures))
            break

        time.sleep(7)  # Stay safely under 10 req/min

        try:
            comp_data = _tracked_get(
                f"{FD_BASE}/competitions/{comp_code}/matches",
                params={"dateFrom": today, "dateTo": today, "status": "SCHEDULED"},
            )
            if not comp_data:
                continue

            new_count = 0
            for m in comp_data.get("matches", []):
                mid = str(m.get("id", ""))
                if mid not in seen_ids:
                    all_fixtures.append(m)
                    seen_ids.add(mid)
                    new_count += 1

            if new_count > 0:
                logger.info("  %s: +%d fixtures", comp_code, new_count)

        except Exception as e:
            logger.warning("Fixture fetch failed for %s: %s", comp_code, e)
            continue

    logger.info("Today's fixtures fetched (total): %d", len(all_fixtures))
    return all_fixtures


def get_standings(competition_code: str) -> Optional[dict]:
    if not _can_call_api():
        return None
    time.sleep(7)
    _call_timestamps.append(time.time())
    return get_json(
        f"{FD_BASE}/competitions/{competition_code}/standings",
        headers=_fd_headers(),
    )


def get_top_scorers(competition_code: str, season: int = None) -> list[dict]:
    if not _can_call_api():
        return []
    params = {}
    if season:
        params["season"] = season
    time.sleep(7)
    _call_timestamps.append(time.time())
    data = get_json(
        f"{FD_BASE}/competitions/{competition_code}/scorers",
        params=params,
        headers=_fd_headers(),
    )
    return data.get("scorers", []) if data else []


def get_match_detail(match_id: int) -> Optional[dict]:
    if not _can_call_api():
        return None
    _call_timestamps.append(time.time())
    return get_json(f"{FD_BASE}/matches/{match_id}", headers=_fd_headers())


# ── TheSportsDB helpers ───────────────────────────────────────────────────────

def _sdb(endpoint: str, params: dict = None):
    key = getattr(settings, "THESPORTSDB_API_KEY", "3")
    url = f"{SDB_BASE}/{key}/{endpoint}"
    return get_json(url, params=params)


def get_team_info(team_name: str) -> Optional[dict]:
    data = _sdb("searchteams.php", {"t": team_name})
    if data and data.get("teams"):
        return data["teams"][0]
    return None


def get_team_logo_url(team_name: str) -> Optional[str]:
    info = get_team_info(team_name)
    return info.get("strTeamBadge") if info else None


def get_player_photo_url(player_name: str) -> Optional[str]:
    data = _sdb("searchplayers.php", {"p": player_name})
    if data and data.get("player"):
        p = data["player"][0]
        return p.get("strThumb") or p.get("strCutout")
    return None


def get_historical_fact_by_date(month: int, day: int) -> list[dict]:
    data = _sdb(f"eventsonthisday.php?month={month}&day={day}&l=Soccer")
    return data.get("events", []) if data else []


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


# ── Normalisers ───────────────────────────────────────────────────────────────

def normalise_match(raw: dict) -> dict:
    competition = raw.get("competition", {})
    home  = raw.get("homeTeam", {})
    away  = raw.get("awayTeam", {})
    score = raw.get("score", {})
    full  = score.get("fullTime", {})
    half  = score.get("halfTime", {})

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
