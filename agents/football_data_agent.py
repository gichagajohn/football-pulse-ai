"""
agents/football_data_agent.py — Football Pulse AI
Collects football data from Football-Data.org, TheSportsDB, and RSS feeds.

FIXES applied:
  - get_todays_fixtures() now uses ONE global API call instead of 8 per-competition
    calls. This stops the 429 rate-limit storm that burned all 10 req/min.
  - Per-competition fallback only runs if the global call returns 0 results,
    AND only for competitions not already seen, with a 7-second delay between each.
  - get_live_matches() same pattern — global first, targeted fallback only if needed.
  - Added _can_call_api() guard using a simple in-memory rate limit counter.
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

# Competitions on the free tier that we care about
WATCHED_COMPETITIONS = ["WC", "CL", "PL", "PD", "BL1", "SA", "FL1", "EC"]

# Simple in-process rate limiter: max 9 calls/minute (safe under the 10/min limit)
_call_timestamps: list[float] = []
_RATE_LIMIT     = 9     # calls
_RATE_WINDOW    = 60.0  # seconds


def _fd_headers() -> dict:
    return {"X-Auth-Token": settings.FOOTBALL_DATA_API_KEY}


def _can_call_api() -> bool:
    """
    Return True if we are within the rate limit, False if we would exceed it.
    Cleans up timestamps older than the window automatically.
    """
    now = time.time()
    # Drop timestamps outside the window
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
    """
    Wrapper around get_json that records the call timestamp for rate limiting.
    Returns None if rate limit reached.
    """
    if not _can_call_api():
        return None
    _call_timestamps.append(time.time())
    return get_json(url, params=params, headers=_fd_headers())


def get_live_matches() -> list[dict]:
    """
    Return matches currently in progress.

    Strategy (saves API calls):
      1. ONE global /matches?status=IN_PLAY call — covers all competitions.
      2. Only if that returns 0 results, try the World Cup specifically
         (WC is sometimes missed by the global endpoint).
      3. No other per-competition calls during live polling.
    """
    all_matches = []

    # ── Step 1: Global call ───────────────────────────────────
    data = _tracked_get(f"{FD_BASE}/matches", params={"status": "IN_PLAY"})
    if data:
        all_matches.extend(data.get("matches", []))

    logger.info("Live matches fetched: %d", len(all_matches))

    # ── Step 2: World Cup targeted fallback (only if nothing live) ──
    if not all_matches:
        if _can_call_api():
            time.sleep(7)   # Respect rate limit before second call
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
    Return today's scheduled matches.

    Strategy (saves API calls):
      1. ONE global /matches?dateFrom=today&dateTo=today call.
         This returns ALL competitions in a single request.
      2. Only if the global call returns 0 (e.g. during the World Cup
         when some comps are unlisted), attempt WC-specific call only.
      3. No loop over all 8 competitions — that was causing all 429 errors.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_fixtures = []
    seen_ids: set[str] = set()

    # ── Step 1: One global call ───────────────────────────────
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

    logger.info("Today's fixtures fetched: %d", len(all_fixtures))

    # ── Step 2: WC fallback only ──────────────────────────────
    # The World Cup is sometimes excluded from the global endpoint
    # during the tournament. One targeted call is enough.
    if not all_fixtures and _can_call_api():
        time.sleep(7)
        wc_data = _tracked_get(
            f"{FD_BASE}/competitions/WC/matches",
            params={"dateFrom": today, "dateTo": today},
        )
        if wc_data:
            for m in wc_data.get("matches", []):
                mid = str(m.get("id", ""))
                if mid not in seen_ids:
                    all_fixtures.append(m)
                    seen_ids.add(mid)
            logger.info(
                "WC fixtures added: %d (total: %d)",
                len(wc_data.get("matches", [])), len(all_fixtures),
            )

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


# ── TheSportsDB helpers (no rate limit concern — free & generous) ──

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


# ── Normalisers ───────────────────────────────────────────────

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
