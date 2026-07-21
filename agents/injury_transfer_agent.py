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


def _looks_like_club(candidate: str) -> bool:
    """
    True if `candidate` is (or is part of) a known club name.
    Checks both directions: candidate could be the full club name,
    or a short form / partial mention of it (e.g. "Villa" -> "Aston Villa").
    """
    cand_low = candidate.lower().strip()
    if not cand_low:
        return False
    for c in KNOWN_CLUBS:
        c_low = c.lower()
        if cand_low == c_low or cand_low in c_low or c_low in cand_low:
            return True
    return False


def _clubs_in_text_order(text: str) -> list:
    """
    Return known clubs mentioned in `text`, ordered by where they first
    appear in the text (not by their position in KNOWN_CLUBS) — so
    from/to assignment reflects the actual sentence, not list order.
    """
    text_low = text.lower()
    found = []
    for c in KNOWN_CLUBS:
        idx = text_low.find(c.lower())
        if idx != -1:
            found.append((idx, c))
    found.sort(key=lambda pair: pair[0])
    return [c for _, c in found]


def _extract_player_and_clubs(title: str, summary: str) -> tuple:
    text = f"{title} {summary}"
    found_clubs = _clubs_in_text_order(text)

    player = ""
    player_match = re.match(
        r"^([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+){0,3})\s+"
        r"(?:signs?|joins?|completes?|moves?|heads?|set to|agrees?|to join|to sign|agrees)",
        title
    )
    if player_match:
        candidate = player_match.group(1).strip()
        if not _looks_like_club(candidate):
            player = candidate

    if not player or len(player) < 3:
        words = title.split()
        cap_words = []
        for w in words[:5]:
            clean = re.sub(r"[^a-zA-Z\-\']", "", w)
            if clean and clean[0].isupper() and len(clean) > 1:
                cap_words.append(clean)
            else:
                break
        candidate = " ".join(cap_words[:2]) if cap_words else "Player TBC"
        player = candidate if not _looks_like_club(candidate) else "Player TBC"

    from_club = found_clubs[0] if len(found_clubs) >= 2 else "Unknown"
    to_club   = found_clubs[1] if len(found_clubs) >= 2 else (found_clubs[0] if found_clubs else "Unknown")

    # NOTE: (?i:...) scopes case-insensitivity to the keyword group ONLY.
    # Previously a trailing re.IGNORECASE flag on the whole pattern silently
    # disabled the [A-Z] capital-letter check, letting lowercase verb
    # fragments (e.g. "sign Garnacho") get captured as club names.
    to_match = re.search(
        r"(?i:to|joins?|heading to|move to|signs? for)\s+([A-Z][a-zA-Z\s]{2,25}?)(?:\s+for|\s+on|\.|,|$)",
        title
    )
    from_match = re.search(
        r"(?i:from|leaves?|departing)\s+([A-Z][a-zA-Z\s]{2,25}?)(?:\s+to|\s+for|\.|,|$)",
        title
    )

    if to_match:
        cand = to_match.group(1).strip()
        matched = next((c for c in KNOWN_CLUBS if c.lower() in cand.lower()), None)
        if matched:
            to_club = matched
        elif cand and cand.split()[0].istitle() and len(cand) < 25:
            to_club = cand

    if from_match:
        cand = from_match.group(1).strip()
        matched = next((c for c in KNOWN_CLUBS if c.lower() in cand.lower()), None)
        if matched:
            from_club = matched

    return player or "Player TBC", from_club, to_club


def _extract_fee(text: str) -> str:
    m = re.search(
        r"(free transfer|undisclosed|[€£$]\s*\d+[\d,.]*\s*(?:m(?:illion)?|bn|k)?|\d+\s*million)",
        text, re.IGNORECASE
    )
    return m.group(0).strip() if m else "Undisclosed"


def _article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _story_key(player: str, to_club: str) -> str:
    """
    Semantic dedup key for a transfer story — same player + destination
    club counts as the same story even if two different articles (and
    therefore two different URLs/art_ids) cover it.
    """
    return f"{player.strip().lower()}|{to_club.strip().lower()}"


def scan_for_news():
    logger.debug("Scanning RSS feeds...")
    processed = 0
    skipped_low_confidence = 0

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

            if TRANSFER_KEYWORDS.search(text):
                logger.info("Transfer article detected: %s", title[:80])
                if decision.should_post("TRANSFER_ALERT", "default", dedup_key=art_id):
                    player, from_club, to_club = _extract_player_and_clubs(title, summary)
                    fee = _extract_fee(text)
                    logger.info("Extracted: player=%s from=%s to=%s", player, from_club, to_club)

                    # Confidence gate: don't publish a guess. If we couldn't
                    # confidently pull a real player name (not a club) or a
                    # destination club, skip the post entirely rather than
                    # publish garbled/wrong info.
                    if player == "Player TBC" or to_club == "Unknown":
                        logger.warning(
                            "Skipping low-confidence transfer post: %s", title[:80]
                        )
                        skipped_low_confidence += 1
                        continue

                    # Semantic dedup: two different articles/URLs about the
                    # same player+destination should only post once.
                    story_key = _story_key(player, to_club)
                    if decision.is_duplicate("TRANSFER_ALERT_STORY", story_key):
                        logger.info(
                            "Skipping duplicate transfer story (already posted): %s to %s",
                            player, to_club
                        )
                        continue

                    try:
                        cap = caption_agent.generate_transfer_caption(player, from_club, to_club, fee)
                        db_id = publisher_agent.create_post_record(0, "", cap)
                        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
                        decision.record_post("TRANSFER_ALERT", art_id, "default", fb_id)
                        decision.record_post("TRANSFER_ALERT_STORY", story_key, "default", fb_id)
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

    logger.info(
        "News scan complete. %d posts generated, %d skipped for low confidence.",
        processed, skipped_low_confidence
    )
    return processed
