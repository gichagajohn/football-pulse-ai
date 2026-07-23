"""
agents/injury_transfer_agent.py — Football Pulse AI
Monitors RSS feeds for transfer and injury news.
Posts text-only to Facebook — no poster generation.

FIXES applied:
  1. Better player name extraction — reads article body, not just headline
  2. Non-football filter — blocks cricket, rugby, tennis etc.
  3. Confidence scoring — skips posts where extraction is too uncertain
  4. Cleaner entity logic — handles "X signs Y", "Y joins X", "X, 40, signs"
"""

import re
import hashlib

import feedparser

import settings
from utils.logger import setup_logger
from agents import content_decision_agent as decision
from agents import caption_agent
from agents import publisher_agent

logger = setup_logger("injury_transfer_agent")

# ── Keyword matchers ──────────────────────────────────────────

TRANSFER_KEYWORDS = re.compile(
    r"\b(signs?|signed|transfer(red)?|joins?|joined|done deal|deal done|"
    r"fee|moves? to|officially|completed|agreement|contract|announce[sd]?|"
    r"on loan|loan deal|permanent|swap deal)\b",
    re.IGNORECASE,
)

INJURY_KEYWORDS = re.compile(
    r"\b(injur(y|ed|ies)|hamstring|ligament|muscle|surgery|ruled out|"
    r"sidelined|out for|fitness|doubt|recovery|setback|fracture|scan|"
    r"concussion|torn|sprain)\b",
    re.IGNORECASE,
)

# ── Hard filter: block non-football sports entirely ───────────
# These slip through because injury/transfer words appear in all sports
NON_FOOTBALL_FILTER = re.compile(
    r"\b(cricket|rugby|tennis|basketball|nba|nfl|nhl|baseball|golf|"
    r"F1|formula.?1|cycling|boxing|mma|ufc|hundred|test match|odi|"
    r"innings|wicket|over|county cricket|sunrisers|mi london|"
    r"stumps?|lbw|bowled)\b",
    re.IGNORECASE,
)

# ── Clubs list (expanded) ─────────────────────────────────────
KNOWN_CLUBS = {
    # England
    "Arsenal", "Chelsea", "Liverpool", "Manchester United", "Manchester City",
    "Tottenham", "Newcastle", "Aston Villa", "West Ham", "Everton",
    "Brighton", "Brentford", "Crystal Palace", "Fulham", "Wolves",
    "Nottingham Forest", "Bournemouth", "Leicester", "Leeds", "Southampton",
    # Spain
    "Real Madrid", "Barcelona", "Atletico Madrid", "Sevilla", "Valencia",
    "Villarreal", "Real Sociedad", "Athletic Bilbao", "Betis",
    # Germany
    "Bayern Munich", "Borussia Dortmund", "RB Leipzig", "Bayer Leverkusen",
    "Eintracht Frankfurt", "Wolfsburg",
    # Italy
    "Juventus", "AC Milan", "Inter Milan", "Napoli", "Roma", "Lazio",
    "Atalanta", "Fiorentina",
    # France
    "PSG", "Paris Saint-Germain", "Monaco", "Lyon", "Marseille", "Lille",
    # Portugal
    "Benfica", "Porto", "Sporting CP",
    # Netherlands
    "Ajax", "PSV", "Feyenoord",
    # Scotland
    "Rangers", "Celtic",
    # Saudi / Other
    "Al-Nassr", "Al-Hilal", "Al-Ahli", "Al-Ittihad",
    # Generic
    "Villa",  # alias for Aston Villa
}

# Canonical name fixes (alias → full name)
CLUB_ALIASES = {
    "Villa":  "Aston Villa",
    "Spurs":  "Tottenham",
    "United": "Manchester United",
    "City":   "Manchester City",
    "PSG":    "Paris Saint-Germain",
}

# ── Patterns that reliably name a player in the headline ──────
# Ordered from most to least specific — first match wins.
PLAYER_PATTERNS = [
    # MOST SPECIFIC FIRST — prevents generic patterns grabbing team names

    # "Modric, 40, signs new AC Milan deal"  →  Modric
    re.compile(
        r"^([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+)?)"
        r",\s*\d{1,2},\s*"
        r"(?:signs?|joins?|moves?|agrees?|completes?|seals?)",
        re.IGNORECASE,
    ),
    # "Rangers confirm Dragojevic signing"  →  Dragojevic
    re.compile(
        r"\bconfirm\s+([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+)?)\s+signing\b",
        re.IGNORECASE,
    ),
    # "West Ham agree deal with Al Hilal for Summerville"  →  Summerville
    re.compile(
        r"\bfor\s+([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+)?)\s*$",
        re.IGNORECASE,
    ),
    # "Arsenal complete deal to sign winger Tzolis"  →  Tzolis
    re.compile(
        r"(?:sign(?:ing)?|signing\s+of|deal\s+(?:for|to\s+sign)|"
        r"moves?\s+for|swoop\s+for)\s+"
        r"(?:winger|striker|midfielder|defender|keeper|goalkeeper|"
        r"forward|playmaker|fullback|centre.?back|centre.?forward)?\s*"
        r"([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+)?)",
        re.IGNORECASE,
    ),
    # "Garnacho joins Villa on loan from Chelsea"  →  Garnacho
    re.compile(
        r"^([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+)?)"
        r"\s+(?:joins?|signs?|moves?|agrees?|completes?|seals?|heads?|"
        r"set to join|to join|to sign for|on loan)\b",
        re.IGNORECASE,
    ),
    # "X signs new deal" / "X signs contract extension"
    re.compile(
        r"^([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+)?)"
        r"\s+signs?\s+(?:new|fresh|contract|deal|extension)\b",
        re.IGNORECASE,
    ),
]

# Words that look like names but are NOT player names
FALSE_POSITIVES = {
    "why", "how", "what", "when", "who", "where",
    "rangers", "celtic", "arsenal", "chelsea", "liverpool",
    "manchester", "tottenham", "newcastle", "villa", "west",
    "real", "barcelona", "juventus", "milan", "united",
    "city", "premier", "league", "transfer", "loan",
    "confirmed", "official", "done", "deal", "sources",
    "report", "reports", "latest", "update", "news",
    "goalkeeper", "winger", "striker", "midfielder",
    "defender", "forward", "playmaker",
}


def _normalise_club(name: str) -> str:
    """Expand club aliases to full names."""
    return CLUB_ALIASES.get(name, name)


def _find_clubs_in_text(text: str) -> list[str]:
    """Return list of known clubs mentioned in text, in order of appearance."""
    found = []
    text_lower = text.lower()
    # Sort longest first so "Manchester United" matches before "United"
    for club in sorted(KNOWN_CLUBS, key=len, reverse=True):
        if club.lower() in text_lower and _normalise_club(club) not in found:
            found.append(_normalise_club(club))
    return found


def _extract_player_name(title: str, summary: str = "") -> str:
    """
    Try each PLAYER_PATTERNS regex against the headline.
    Falls back to scanning the summary for capitalised names near verb phrases.
    Returns empty string if nothing confident found.
    """
    # Try structured patterns on title first
    for pattern in PLAYER_PATTERNS:
        m = pattern.search(title)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in FALSE_POSITIVES and len(candidate) >= 3:
                return candidate

    # Fallback: scan summary for "signed X" / "X has signed" etc.
    if summary:
        body = f"{title} {summary}"
        verb_near = re.search(
            r"(?:sign(?:ed|ing)|join(?:ed|ing)|transfer(?:red)?|loan(?:ed)?)"
            r"\s+(?:by\s+|for\s+)?([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+)?)",
            body,
        )
        if verb_near:
            candidate = verb_near.group(1).strip()
            if candidate.lower() not in FALSE_POSITIVES and len(candidate) >= 3:
                return candidate

    return ""   # Couldn't extract confidently


def _extract_transfer_details(title: str, summary: str) -> tuple[str, str, str]:
    """
    Returns (player_name, from_club, to_club).
    All three can be empty strings if not found.
    """
    player = _extract_player_name(title, summary)

    full_text  = f"{title}. {summary}"
    clubs      = _find_clubs_in_text(full_text)

    from_club = ""
    to_club   = ""

    # Try explicit directional phrases first
    to_match = re.search(
        r"(?:\bto\b|\bjoins?\b|\bheading to\b|\bsigns? for\b)"
        r"\s+([A-Z][a-zA-Z\s\-]{2,30}?)(?:\s+(?:for|on|from|in)|\.|,|$)",
        title, re.IGNORECASE,
    )
    from_match = re.search(
        r"(?:\bfrom\b|\bleaves?\b|\bdeparting\b)"
        r"\s+([A-Z][a-zA-Z\s\-]{2,30}?)(?:\s+(?:to|for|on)|\.|,|$)",
        title, re.IGNORECASE,
    )

    if to_match:
        cand = to_match.group(1).strip()
        # See if a known club matches
        to_club = next(
            (_normalise_club(c) for c in KNOWN_CLUBS
             if c.lower() in cand.lower()), ""
        )

    if from_match:
        cand = from_match.group(1).strip()
        from_club = next(
            (_normalise_club(c) for c in KNOWN_CLUBS
             if c.lower() in cand.lower()), ""
        )

    # Fill gaps from the clubs-found list
    if not to_club and not from_club:
        if len(clubs) >= 2:
            from_club = clubs[0]
            to_club   = clubs[1]
        elif len(clubs) == 1:
            to_club = clubs[0]

    elif to_club and not from_club:
        # From = first club that isn't to_club
        from_club = next((c for c in clubs if c != to_club), "")

    elif from_club and not to_club:
        to_club = next((c for c in clubs if c != from_club), "")

    return player, from_club, to_club


def _confidence_ok(player: str, from_club: str, to_club: str) -> bool:
    """
    Require at minimum: a real player name AND at least one club.
    Reject if player looks like a team name or generic word.
    """
    if not player or player.lower() in FALSE_POSITIVES:
        return False
    if len(player.split()) > 4:
        return False   # Probably grabbed a sentence fragment
    if not to_club and not from_club:
        return False
    return True


def _extract_fee(text: str) -> str:
    m = re.search(
        r"(free transfer|undisclosed|"
        r"[€£$]\s*\d+[\d,.]*\s*(?:m(?:illion)?|bn|k)?|"
        r"\d+\s*million|loan)",
        text, re.IGNORECASE,
    )
    return m.group(0).strip() if m else "Undisclosed"


def _article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _is_football_content(title: str, summary: str) -> bool:
    """
    Return False for non-football sport articles (cricket, rugby, etc.).
    Returns True if:
      • No non-football keyword is found, AND
      • Either a football signal word OR a known club name appears in the text.
    """
    text = f"{title} {summary}"

    # Hard block on other sports
    if NON_FOOTBALL_FILTER.search(text):
        return False

    # Football keyword check
    football_signal = re.compile(
        r"\b(football|soccer|premier league|champions league|la liga|"
        r"bundesliga|serie a|ligue 1|fifa|uefa|transfer|footballer|"
        r"manager|goalkeeper|striker|midfielder|defender|winger|"
        r"signing|loan|match|fixture|goal|squad|club|kit|"
        r"signs?|joins?|contract|deal)\b",
        re.IGNORECASE,
    )
    if football_signal.search(text):
        return True

    # Accept if a known club name is mentioned (e.g. "Modric, 40, signs new AC Milan deal")
    text_lower = text.lower()
    return any(club.lower() in text_lower for club in KNOWN_CLUBS)


# ── Main scanner ──────────────────────────────────────────────

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
            title   = (entry.get("title")   or "").strip()
            summary = (entry.get("summary") or "").strip()
            link    = (entry.get("link")    or "").strip()
            text    = f"{title} {summary}"
            art_id  = _article_hash(link)

            if not title:
                continue

            # ── Non-football hard filter ──────────────────────
            if not _is_football_content(title, summary):
                logger.debug("Non-football article skipped: %s", title[:70])
                continue

            if decision.is_duplicate("RSS_ARTICLE", art_id):
                continue

            # ── TRANSFER detection ────────────────────────────
            if TRANSFER_KEYWORDS.search(text):
                logger.info("Transfer article detected: %s", title[:80])

                if decision.should_post("TRANSFER_ALERT", "default", dedup_key=art_id):
                    player, from_club, to_club = _extract_transfer_details(title, summary)
                    fee = _extract_fee(text)

                    logger.info(
                        "Extracted: player=%s  from=%s  to=%s",
                        player or "(unknown)",
                        from_club or "(unknown)",
                        to_club or "(unknown)",
                    )

                    if not _confidence_ok(player, from_club, to_club):
                        logger.warning(
                            "Skipping low-confidence transfer: %s", title[:70]
                        )
                        # Still mark as seen so we don't retry forever
                        decision.record_post("TRANSFER_ALERT", art_id, "default", "skipped")
                        continue

                    try:
                        cap = caption_agent.generate_transfer_caption(
                            player, from_club or "Unknown", to_club or "Unknown", fee
                        )
                        db_id = publisher_agent.create_post_record(0, "", cap)
                        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
                        decision.record_post("TRANSFER_ALERT", art_id, "default", fb_id)
                        processed += 1
                        logger.info("Transfer post published: %s", fb_id)
                    except Exception as e:
                        logger.error("Transfer post failed: %s", e)

                continue   # Don't double-check for injury if we already matched transfer

            # ── INJURY detection ──────────────────────────────
            if INJURY_KEYWORDS.search(text):
                logger.info("Injury article detected: %s", title[:80])

                if decision.should_post("INJURY_ALERT", "default", dedup_key=art_id):
                    try:
                        cap = (
                            f"INJURY UPDATE\n\n"
                            f"{title}\n\n"
                            f"Follow Football Pulse for the latest team news.\n\n"
                            f"#InjuryNews #TeamNews #Football #FootballPulse"
                        )
                        db_id = publisher_agent.create_post_record(0, "", cap)
                        fb_id = publisher_agent.publish(None, cap, post_id_db=db_id)
                        decision.record_post("INJURY_ALERT", art_id, "default", fb_id)
                        processed += 1
                        logger.info("Injury post published: %s", fb_id)
                    except Exception as e:
                        logger.error("Injury post failed: %s", e)

    logger.info("News scan complete. %d posts published.", processed)
    return processed
