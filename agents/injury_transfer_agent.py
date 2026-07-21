"""
agents/injury_transfer_agent.py — Football Pulse AI
Monitors RSS feeds for transfer and injury news.
Posts text-only to Facebook — no poster generation.
"""

import re
import hashlib
from datetime import datetime

import feedparser

import settings
from utils.logger import setup_logger
from agents import content_decision_agent as decision
from agents import caption_agent
from agents import publisher_agent

logger = setup_logger("injury_transfer_agent")

TRANSFER_KEYWORDS = re.compile(
    r"\b(signs?|signed|transfer(red)?|joins?|joined|deal done|done deal|"
    r"fee|moves? to|move to|offici(al|ally)|completed|agreement|contract|announce[sd]?)\b",
    re.IGNORECASE,
)

INJURY_KEYWORDS = re.compile(
    r"\b(injur(y|ed|ies)|hamstring|ligament|muscle|surgery|ruled out|"
    r"sidelined|out for|weeks?|months?|scan|fitness|doubt|recovery|setback)\b",
    re.IGNORECASE,
)

KNOWN_CLUBS = [
    "Real Madrid","Barcelona","Manchester United","Manchester City",
    "Arsenal","Chelsea","Liverpool","Tottenham","Newcastle",
    "Bayern Munich","PSG","Paris Saint-Germain","Juventus","AC Milan",
    "Inter Milan","Atletico Madrid","Borussia Dortmund","Ajax",
    "Porto","Benfica","Napoli","Roma","Lazio","Sevilla",
    "Valencia","Villarreal","Leicester","Aston Villa","West Ham",
    "Everton","Leeds","Wolves","Brighton","Brentford",
    "Crystal Palace","Fulham","Nottingham Forest","Bournemouth",
    "Al-Nassr","Al-Hilal",
]


def _extract_player_and_clubs(title: str, summary: str) -> tuple:
    text = f"{title} {summary}"

    found_clubs = [c for c in KNOWN_CLUBS if c.lower() in text.lower()]

    player = ""
    player_match = re.match(
        r"^([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+){0,3})\s+"
        r"(?:signs?|joins?|completes?|moves?|heads?|set to|agrees?|to join|to sign|agrees)",
        title
    )
    if player_match:
        player = player_match.group(1).strip()

    if not player or len(player) < 3:
        words = title.split()
        cap_words = []
        for w in words[:5]:
            clean = re.sub(r"[^a-zA-Z\-\']", "", w)
            if clean and clean[0].isupper() and len(clean) > 1:
                cap_words.append(clean)
            else:
                break
        player = " ".join(cap_words[:2]) if cap_words else "Player TBC"

    from_club = found_clubs[0] if len(found_clubs) >= 2 else "Unknown"
    to_club   = found_clubs[1] if len(found_clubs) >= 2 else (found_clubs[0] if found_clubs else "Unknown")

    to_match = re.search(
        r"(?:to|joins?|heading to|move to|signs? for)\s+([A-Z][a-zA-Z\s]{2,25})(?:\s+for|\s+on|\.|,|$)",
        title, re.IGNORECASE
    )
    from_match = re.search(
        r"(?:from|leaves?|departing)\s+([A-Z][a-zA-Z\s]{2,25})(?:\s+to|\s+for|\.|,|$)",
        title, re.IGNORECASE
    )

    if to_match:
        cand = to_match.group(1).strip()
        to_club = next((c for c in KNOWN_CLUBS if c.lower() in cand.lower()), cand if len(cand) < 25 else to_club)

    if from_match:
        cand = from_match.group(1).strip()
        from_club = next((c for c in KNOWN_CLUBS if c.lower() in cand.lower()), cand if len(cand) < 25 else from_club)

    return player or "Player TBC", from_club, to_club


def _extract_fee(text: str) -> str:
    m = re.search(
        r"(free transfer|undisclosed|[€£$]\s*\d+[\d,.]*\s*(?:m(?:illion)?|bn|k)?|\d+\s*million)",
        text, re.IGNORECASE
    )
    return m.group(0).strip() if m else "Undisclosed"


def _article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def scan_for_news():
    logger.debug("Scanning RSS feeds...")
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

            if decision.is_duplicate("RSS_ARTICLE", art_id):
                continue

            if TRANSFER_KEYWORDS.search(text):
                logger.info("Transfer article detected: %s", title[:80])
                if decision.should_post("TRANSFER_ALERT", "default", dedup_key=art_id):
                    player, from_club, to_club = _extract_player_and_clubs(title, summary)
                    fee = _extract_fee(text)
                    logger.info("Extracted: player=%s from=%s to=%s", player, from_club, to_club)
                    try:
                        cap = caption_agent.generate_transfer_caption(player, from_club, to_club, fee)
                        db_id = publisher_agent.create_post_record(0, "", cap)
                        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
                        decision.record_post("TRANSFER_ALERT", art_id, "default", fb_id)
                        processed += 1
                        logger.info("Transfer text post published: %s", fb_id)
                    except Exception as e:
                        logger.error("Transfer post failed: %s", e)
                continue

            if INJURY_KEYWORDS.search(text):
                logger.info("Injury article detected: %s", title[:80])
                if decision.should_post("INJURY_ALERT", "default", dedup_key=art_id):
                    try:
                        cap = (
                            f"INJURY NEWS\n\n"
                            f"{title}\n\n"
                            f"Stay tuned to Football Pulse for the latest updates.\n\n"
                            f"#InjuryNews #Football #FootballPulse"
                        )
                        db_id = publisher_agent.create_post_record(0, "", cap)
                        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
                        decision.record_post("INJURY_ALERT", art_id, "default", fb_id)
                        processed += 1
                        logger.info("Injury text post published: %s", fb_id)
                    except Exception as e:
                        logger.error("Injury post failed: %s", e)

    logger.info("News scan complete. %d posts generated.", processed)
    return processed
