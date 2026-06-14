"""
settings.py — Football Pulse AI
Central configuration. All values sourced from .env (or environment).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")


def _env(key: str, default=None, cast=str):
    val = os.getenv(key, default)
    if val is None:
        return val
    try:
        return cast(val)
    except (ValueError, TypeError):
        return default


# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
DB_PATH         = BASE_DIR / _env("DB_PATH", "database/football_pulse.db")
OUTPUT_DIR      = BASE_DIR / _env("OUTPUT_DIR", "output")
POSTER_DIR      = BASE_DIR / _env("POSTER_DIR", "output/posters")
CAPTION_DIR     = BASE_DIR / _env("CAPTION_DIR", "output/captions")
ASSETS_DIR      = BASE_DIR / "assets"
FONTS_DIR       = ASSETS_DIR / "fonts"
LOG_DIR         = BASE_DIR / "logs"

# Ensure directories exist
for d in [DB_PATH.parent, OUTPUT_DIR, POSTER_DIR, CAPTION_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── API Keys ───────────────────────────────────────────────────────────────
FOOTBALL_DATA_API_KEY = _env("FOOTBALL_DATA_API_KEY", "")
THESPORTSDB_API_KEY   = _env("THESPORTSDB_API_KEY", "1")
GROK_API_KEY          = _env("GROK_API_KEY", "")

# ── Meta / Social ──────────────────────────────────────────────────────────
FB_PAGE_ACCESS_TOKEN  = _env("FB_PAGE_ACCESS_TOKEN", "")
FB_PAGE_ID            = _env("FB_PAGE_ID", "")
IG_USER_ID            = _env("IG_USER_ID", "")

# ── Scheduling ─────────────────────────────────────────────────────────────
LIVE_CHECK_INTERVAL       = _env("LIVE_CHECK_INTERVAL",       60,    int)
STANDINGS_CHECK_INTERVAL  = _env("STANDINGS_CHECK_INTERVAL",  900,   int)
FACTS_INTERVAL            = _env("FACTS_INTERVAL",            1800,  int)
HISTORICAL_INTERVAL       = _env("HISTORICAL_INTERVAL",       10800, int)

# ── Content Policy ─────────────────────────────────────────────────────────
MIN_PRIORITY_TO_POST = _env("MIN_PRIORITY_TO_POST", 40,  int)
MAX_POSTS_PER_HOUR   = _env("MAX_POSTS_PER_HOUR",   8,   int)
DEDUPE_WINDOW_HOURS  = _env("DEDUPE_WINDOW_HOURS",  6,   int)

# ── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL   = _env("LOG_LEVEL", "INFO")
TIMEZONE    = _env("TIMEZONE", "UTC")

# ── Competition Priority Map ───────────────────────────────────────────────
COMPETITION_PRIORITY = {
    # FIFA / International
    "FIFA World Cup":              100,
    "UEFA Champions League":        95,
    "UEFA Europa League":           85,
    "UEFA Conference League":       75,
    "AFC Champions League":         75,
    "AFCON":                        80,
    # Top 5 Leagues
    "Premier League":               90,
    "La Liga":                      88,
    "Bundesliga":                   87,
    "Serie A":                      86,
    "Ligue 1":                      85,
    # Other notable
    "MLS":                          70,
    "Saudi Pro League":             72,
    "Eredivisie":                   68,
    "Liga Portugal":                67,
    "Championship":                 65,
    # Default
    "default":                      40,
}

# ── Poster Design Palette ─────────────────────────────────────────────────
DESIGN = {
    "bg_dark":      "#0A0A0F",
    "bg_card":      "#12121A",
    "accent_gold":  "#FFD700",
    "accent_red":   "#E63946",
    "accent_green": "#2DC653",
    "accent_blue":  "#4CC9F0",
    "text_primary": "#FFFFFF",
    "text_muted":   "#8B8B9B",
    "gradient_1":   "#1A1A2E",
    "gradient_2":   "#16213E",
}

# ── RSS Feeds ─────────────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://www.skysports.com/rss/12040",
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.goal.com/feeds/en/news",
    "https://www.espn.com/espn/rss/soccer/news",
]