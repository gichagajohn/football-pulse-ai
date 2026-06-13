"""
agents/injury_transfer_agent.py — Football Pulse AI
Monitors RSS feeds for transfer and injury news, generates posts automatically.
Detects keywords and routes to the correct poster + caption type.
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

# ─────────────────────────────────────────────────────────────────────────────
# Player / club name extractor (simple heuristic)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_clubs(text: str) -> tuple[str, str]:
    """
    Very simple heuristic: look for "Club A to Club B" or "from Club A".
    Returns (from_club, to_club) or ("Unknown", "Unknown").
    """
    # Pattern: "X to Y" or "X joins Y"
    m = re.search(r"(\w[\w\s]+?)\s+(?:to|joins?)\s+([\w\s]+?)(?:\s+for|\s+on|\.|,|$)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "Unknown Club", "Unknown Club"


def _extract_fee(text: str) -> str:
    """Extract fee string like '€50m', '£30 million', 'free transfer'."""
    m = re.search(
        r"(free transfer|undisclosed|[€£$]\s*\d+[\d,.]*\s*(?:m(?:illion)?|bn|k)?|\d+\s*million)",
        text, re.IGNORECASE
    )
    return m.group(0).strip() if m else "Undisclosed"


def _article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# Main scanner
# ─────────────────────────────────────────────────────────────────────────────

def scan_for_news():
    """
    Pull all RSS feeds, detect transfer/injury articles, generate posts.
    Called by the scheduler every 30 minutes.
    """
    logger.debug("Scanning RSS feeds for transfer/injury news…")
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

            art_id  = _article_hash(link)

            # Skip if already processed
            if decision.is_duplicate(art_id, "RSS_ARTICLE"):
                continue

            # ── Transfer detection ─────────────────────────────────────
            if TRANSFER_KEYWORDS.search(text):
                logger.info("Transfer article detected: %s", title[:80])
                should, priority = decision.should_post("TRANSFER_ALERT", "default")
                if should and decision.within_rate_limit():
                    from_club, to_club = _extract_clubs(text)
                    fee = _extract_fee(text)

                    # Use headline as player name heuristic (first capitalized words)
                    player_match = re.match(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", title)
                    player = player_match.group(1) if player_match else title[:30]

                    try:
                        poster_path = poster.create_transfer_alert(
                            player_name = player,
                            from_club   = from_club,
                            to_club     = to_club,
                            fee         = fee,
                        )
                        cap = caption_agent.generate_transfer_caption(player, from_club, to_club, fee)
                        db_id = publisher_agent.create_post_record(0, poster_path, cap)
                        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
                        processed += 1
                    except Exception as e:
                        logger.error("Transfer post failed: %s", e)

                decision.record_post(art_id, "RSS_ARTICLE")
                continue

            # ── Injury detection ────────────────────────────────────────
            if INJURY_KEYWORDS.search(text):
                logger.info("Injury article detected: %s", title[:80])
                should, priority = decision.should_post("INJURY_UPDATE", "default")
                if should and decision.within_rate_limit():
                    try:
                        fact_text = title[:120]
                        poster_path = poster.create_football_fact(
                            fact_text, category="INJURY UPDATE", emoji="🚑"
                        )
                        cap = (
                            f"🚑 INJURY NEWS\n\n{title}\n\n"
                            f"Stay tuned for updates. 👇\n\n"
                            f"#InjuryNews #Football #FootballPulse"
                        )
                        db_id = publisher_agent.create_post_record(0, poster_path, cap)
                        publisher_agent.publish(poster_path, cap, post_id_db=db_id)
                        processed += 1
                    except Exception as e:
                        logger.error("Injury post failed: %s", e)

                decision.record_post(art_id, "RSS_ARTICLE")

    logger.info("News scan complete. %d posts generated.", processed)
    return processed
