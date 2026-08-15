"""
agents/injury_transfer_agent.py — Football Pulse AI
Monitors RSS feeds for transfer and injury news, generates posts automatically.

DEDUP RULES:
  - Each player gets ONE transfer post per day maximum.
  - Each player gets ONE injury post per day maximum.
  - Duplicate articles about the same player from different RSS sources are ignored.
  - Low-confidence extractions (unknown player/clubs) are skipped.
"""

import re
import hashlib
from datetime import datetime

import feedparser

import settings
from utils.logger import setup_logger
from agents import content_decision_agent as decision
from agents import poster_design_agent    as poster
from agents import caption_agent
from agents import publisher_agent

logger = setup_logger("injury_transfer_agent")

# ─────────────────────────────────────────────────────────────────────────────
# Keyword patterns
# ─────────────────────────────────────────────────────────────────────────────

TRANSFER_KEYWORDS = re.compile(
    r"\b(signs?|signed|transfer(red)?|joins?|joined|deal done|done deal|"
    r"fee|moves? to|move to|offici(al|ally)|completed|agreement|contract)\b",
    re.IGNORECASE,
)

INJURY_KEYWORDS = re.compile(
    r"\b(injur(y|ed|ies)|hamstring|ligament|muscle|surgery|ruled out|"
    r"sidelined|out for|weeks?|months?|scan|fitness|doubt|recovery|setback)\b",
    re.IGNORECASE,
)

# Known clubs for confidence checking
KNOWN_CLUBS = {
    "Arsenal", "Chelsea", "Liverpool", "Manchester City", "Manchester United",
    "Tottenham", "Newcastle", "Aston Villa", "West Ham", "Brighton",
    "Real Madrid", "Barcelona", "Atletico Madrid",
    "Bayern Munich", "Borussia Dortmund", "RB Leipzig",
    "PSG", "Paris Saint-Germain",
    "Juventus", "AC Milan", "Inter Milan", "Napoli",
    "Ajax", "Porto", "Benfica",
    "Inter", "Spurs", "City", "United", "Barca", "Madrid",
}

# ─────────────────────────────────────────────────────────────────────────────
# Extractors
# ─────────────────────────────────────────────────────────────────────────────

def _extract_player_name(title: str) -> str:
    """
    Extract the most likely player name from a transfer/injury headline.
    Returns a normalised lowercase key for dedup purposes.
    """
    # Remove common prefixes like "DONE DEAL:", "OFFICIAL:", etc.
    title = re.sub(r"^(done deal|official|breaking|confirmed|transfer news)[:\s!-]*",
                   "", title, flags=re.IGNORECASE).strip()

    # Try to grab the first 1-3 capitalised words as the player name
    m = re.match(r"([A-Z][a-z]+(?:[\s-][A-Z][a-z]+){0,2})", title)
    if m:
        name = m.group(1).strip()
        # Reject if it's clearly a club name or generic word
        if name not in KNOWN_CLUBS and len(name) > 3:
            return name.lower()

    return ""


def _extract_clubs(text: str) -> tuple[str, str]:
    """
    Extract (from_club, to_club) from transfer text.
    Returns ("", "") if not found with reasonable confidence.
    """
    # Pattern: "X to Y" or "X joins Y" or "from X to Y"
    patterns = [
        r"from\s+([\w\s]+?)\s+(?:to|join(?:s|ing)?)\s+([\w\s]+?)(?:\s+for|\s+on|\.|,|$)",
        r"([\w\s]+?)\s+(?:to|join(?:s|ing)?)\s+([\w\s]+?)(?:\s+for|\s+on|\.|,|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            from_c = m.group(1).strip()
            to_c   = m.group(2).strip()
            # Only return if at least one side is a known club
            if from_c in KNOWN_CLUBS or to_c in KNOWN_CLUBS:
                return from_c, to_c

    return "", ""


def _extract_fee(text: str) -> str:
    m = re.search(
        r"(free transfer|undisclosed|[€£$]\s*\d+[\d,.]*\s*(?:m(?:illion)?|bn|k)?|\d+\s*million)",
        text, re.IGNORECASE
    )
    return m.group(0).strip() if m else "Undisclosed"


def _article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _player_day_key(player_name: str, event_type: str) -> str:
    """
    Unique key for a player + event type + today's date.
    This is what prevents the same player being posted multiple times per day.
    """
    today = datetime.now().strftime("%Y%m%d")
    safe  = re.sub(r"\W+", "_", player_name.lower().strip())
    return f"{event_type}_{safe}_{today}"


# ─────────────────────────────────────────────────────────────────────────────
# Main scanner
# ─────────────────────────────────────────────────────────────────────────────

def scan_for_news():
    """
    Pull all RSS feeds, detect transfer/injury articles, generate posts.
    Each player gets at most ONE transfer post and ONE injury post per day.
    """
    logger.debug("Scanning RSS feeds for transfer/injury news...")
    processed = 0

    for feed_url in settings.RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            logger.warning("Feed parse error (%s): %s", feed_url, e)
            continue

        for entry in feed.entries[:15]:
            title   = entry.get("title", "")
            summary = entry.get("summary", "")
            link    = entry.get("link", "")
            text    = f"{title} {summary}"

            # Mark this article URL as seen so we don't reprocess it
            art_id = _article_hash(link)
            if decision.is_duplicate(art_id, "RSS_ARTICLE"):
                continue

            # ── Transfer detection ─────────────────────────────────────
            if TRANSFER_KEYWORDS.search(text):
                logger.info("Transfer article detected: %s", title[:80])

                player_name = _extract_player_name(title)
                from_club, to_club = _extract_clubs(text)
                fee = _extract_fee(text)

                # Skip if we can't extract a real player name
                if not player_name:
                    logger.warning("Skipping: could not extract player name from: %s", title[:60])
                    decision.record_post(art_id, "RSS_ARTICLE")
                    continue

                # Skip if clubs are unknown/unextractable
                if not from_club and not to_club:
                    logger.warning("Skipping low-confidence transfer: %s", title[:60])
                    decision.record_post(art_id, "RSS_ARTICLE")
                    continue

                logger.info("Extracted: player=%s  from=%s  to=%s", player_name, from_club, to_club)

                # ── PLAYER-LEVEL DEDUP: one post per player per day ───
                player_key = _player_day_key(player_name, "TRANSFER")
                if decision.is_duplicate(player_key, "PLAYER_TRANSFER_DAY"):
                    logger.info("Already posted transfer for '%s' today — skipping.", player_name)
                    decision.record_post(art_id, "RSS_ARTICLE")
                    continue

                # Rate limit check
                if not decision.within_rate_limit():
                    logger.warning("Rate limit reached — skipping transfer post.")
                    break

                try:
                    poster_path = poster.create_transfer_alert(
                        player_name = player_name.title(),
                        from_club   = from_club or "Unknown",
                        to_club     = to_club   or "Unknown",
                        fee         = fee,
                    )
                    cap = caption_agent.generate_transfer_caption(
                        player_name.title(), from_club or "Unknown", to_club or "Unknown", fee
                    )
                    db_id = publisher_agent.create_post_record(None, poster_path, cap)
                    fb_id = publisher_agent.publish(poster_path, cap, post_id_db=db_id)
                    logger.info("Transfer post published: %s", fb_id)

                    # Record both the article and the player-day key
                    decision.record_post(art_id, "RSS_ARTICLE")
                    decision.record_post(player_key, "PLAYER_TRANSFER_DAY")
                    processed += 1

                except Exception as e:
                    logger.error("Transfer post failed: %s", e)
                    decision.record_post(art_id, "RSS_ARTICLE")

                continue

            # ── Injury detection ────────────────────────────────────────
            if INJURY_KEYWORDS.search(text):
                logger.info("Injury article detected: %s", title[:80])

                player_name = _extract_player_name(title)

                if not player_name:
                    logger.warning("Skipping injury: could not extract player name from: %s", title[:60])
                    decision.record_post(art_id, "RSS_ARTICLE")
                    continue

                # ── PLAYER-LEVEL DEDUP: one injury post per player per day ──
                player_key = _player_day_key(player_name, "INJURY")
                if decision.is_duplicate(player_key, "PLAYER_INJURY_DAY"):
                    logger.info("Already posted injury for '%s' today — skipping.", player_name)
                    decision.record_post(art_id, "RSS_ARTICLE")
                    continue

                if not decision.within_rate_limit():
                    logger.warning("Rate limit reached — skipping injury post.")
                    break

                try:
                    fact_text = title[:120]
                    poster_path = poster.create_football_fact(
                        fact_text, category="INJURY UPDATE", emoji=""
                    )
                    cap = (
                        f"INJURY NEWS\n\n{title}\n\n"
                        f"Stay tuned for updates.\n\n"
                        f"#InjuryNews #Football #FootballPulse"
                    )
                    db_id = publisher_agent.create_post_record(None, poster_path, cap)
                    fb_id = publisher_agent.publish(poster_path, cap, post_id_db=db_id)
                    logger.info("Injury post published: %s", fb_id)

                    decision.record_post(art_id, "RSS_ARTICLE")
                    decision.record_post(player_key, "PLAYER_INJURY_DAY")
                    processed += 1

                except Exception as e:
                    logger.error("Injury post failed: %s", e)
                    decision.record_post(art_id, "RSS_ARTICLE")

    logger.info("News scan complete. %d posts published.", processed)
    return processed
