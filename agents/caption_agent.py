"""
agents/caption_agent.py — Football Pulse AI
Generates captions, hashtags, and engagement questions.
Uses Google Gemini AI if GEMINI_API_KEY is set, otherwise falls back to templates.

FIXES applied:
  - Gemini prompts shortened and constrained to avoid MAX_TOKENS cutoff
  - Added finishReason check — falls back if response is incomplete
  - maxOutputTokens reduced to 180 (was 300, kept getting cut)
  - Prompt now explicitly says "max 120 words" to keep Gemini focused
"""

import random
import re
from typing import Optional

import settings
from utils.logger import setup_logger

logger = setup_logger("caption_agent")

# ── Hashtag banks ─────────────────────────────────────────────

BASE_TAGS = ["#FootballPulse", "#Football", "#Soccer", "#FootballNews"]

COMPETITION_TAGS = {
    "Premier League":        ["#PremierLeague", "#EPL"],
    "La Liga":               ["#LaLiga"],
    "UEFA Champions League": ["#UCL", "#ChampionsLeague"],
    "UEFA Europa League":    ["#UEL", "#EuropaLeague"],
    "FIFA World Cup":        ["#WorldCup", "#FIFA", "#WorldCup2026"],
    "Bundesliga":            ["#Bundesliga"],
    "Serie A":               ["#SerieA"],
    "Ligue 1":               ["#Ligue1"],
    "MLS":                   ["#MLS"],
}

TEAM_TAG_OVERRIDES = {
    "Liverpool":          "#LFC",
    "Manchester City":    "#MCFC",
    "Manchester United":  "#MUFC",
    "Arsenal":            "#AFC",
    "Chelsea":            "#CFC",
    "Tottenham":          "#THFC",
    "Real Madrid":        "#RealMadrid",
    "Barcelona":          "#FCBarcelona",
    "Bayern Munich":      "#FCBayern",
    "PSG":                "#PSG",
    "Juventus":           "#Juventus",
    "AC Milan":           "#ACMilan",
    "Inter Milan":        "#Inter",
    "Borussia Dortmund":  "#BVB",
    "Aston Villa":        "#AVFC",
    "Newcastle":          "#NUFC",
}

ENGAGEMENT_QUESTIONS = {
    "GOAL":            [
        "Who was your Man of the Match?",
        "Was that a quality finish?",
        "Did you see that coming?",
    ],
    "FULLTIME":        [
        "Fair result? Tell us below!",
        "Rate this match out of 10!",
        "Who was the standout performer?",
    ],
    "TRANSFER_ALERT":  [
        "Good signing or overpay?",
        "Will this transfer work out?",
        "Smart business or panic buy?",
    ],
    "LEAGUE_TABLE":    [
        "Who wins the title? Drop your prediction!",
        "Any surprises in the table?",
    ],
    "TOP_SCORERS":     [
        "Who wins the Golden Boot?",
        "Which striker impresses you most?",
    ],
    "MATCHDAY":        [
        "Who are you backing today?",
        "Score prediction? Drop it below!",
    ],
    "FOOTBALL_FACT":   [
        "Did you know that? Share with a football fan!",
        "What is your favourite football fact?",
    ],
    "default":         [
        "What do you think? Let us know below!",
        "Share this with a fellow football fan!",
    ],
}

# ── Caption templates ─────────────────────────────────────────

GOAL_TEMPLATES = [
    "GOAL! {scorer} finds the net for {team}!\n\n"
    "{home_team} {home_score} - {away_score} {away_team}\n"
    "{minute}' | {competition}\n\n"
    "{engagement}\n{hashtags}",

    "{minute}' — {scorer} SCORES for {team}!\n\n"
    "{home_team} {home_score} - {away_score} {away_team} | {competition}\n\n"
    "{engagement}\n{hashtags}",
]

FULLTIME_TEMPLATES = [
    "FULL TIME!\n\n"
    "{home_team} {home_score} - {away_score} {away_team}\n"
    "{competition}\n\n"
    "{goals_summary}"
    "{engagement}\n{hashtags}",

    "IT'S ALL OVER!\n\n"
    "{home_team} {home_score} - {away_score} {away_team}\n\n"
    "{goals_summary}"
    "{engagement}\n{hashtags}",
]

TRANSFER_TEMPLATES = [
    "TRANSFER NEWS!\n\n"
    "{player} is heading to {to_club}!\n\n"
    "From: {from_club}\n"
    "To: {to_club}\n"
    "Fee: {fee}\n\n"
    "{engagement}\n{hashtags}",

    "DONE DEAL! {player} signs for {to_club}!\n\n"
    "{from_club} → {to_club}\n"
    "Fee: {fee}\n\n"
    "{engagement}\n{hashtags}",
]

MATCHDAY_TEMPLATES = [
    "MATCHDAY!\n\n"
    "{home_team} vs {away_team}\n"
    "{kickoff_time} | {competition}\n"
    "{venue}\n\n"
    "{engagement}\n{hashtags}",
]

FACT_TEMPLATES = [
    "FOOTBALL FACT\n\n{fact_text}\n\n{engagement}\n{hashtags}",
    "DID YOU KNOW?\n\n{fact_text}\n\n{engagement}\n{hashtags}",
]


# ── Helpers ───────────────────────────────────────────────────

def _team_hashtag(team_name: str) -> str:
    if team_name in TEAM_TAG_OVERRIDES:
        return TEAM_TAG_OVERRIDES[team_name]
    return "#" + re.sub(r"\s+", "", team_name)


def build_hashtags(event_type: str, competition: str = None,
                   teams: list = None) -> str:
    tags = list(BASE_TAGS)
    if competition:
        tags += COMPETITION_TAGS.get(competition, [])
    if teams:
        tags += [_team_hashtag(t) for t in teams if t and t != "Unknown"]
    seen = set()
    unique = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return " ".join(unique[:10])   # Cap at 10 tags


def _engagement(event_type: str) -> str:
    pool = ENGAGEMENT_QUESTIONS.get(event_type, ENGAGEMENT_QUESTIONS["default"])
    return random.choice(pool)


# ── Gemini AI ─────────────────────────────────────────────────

def generate_with_gemini(prompt: str) -> Optional[str]:
    """
    Call Gemini free tier (gemini-2.5-flash).
    Returns None if unavailable, quota hit, or response incomplete.

    Key fix: maxOutputTokens=180, and we reject any response where
    finishReason != "STOP" (catches MAX_TOKENS truncation).
    """
    gemini_key = (
        getattr(settings, "GEMINI_API_KEY", None)
        or __import__("os").getenv("GEMINI_API_KEY", "")
    )
    if not gemini_key:
        return None

    try:
        import requests
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={gemini_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 180,   # Tight limit — forces concise output
                    "temperature": 0.75,
                },
                "systemInstruction": {
                    "parts": [{
                        "text": (
                            "You are a football social media writer. "
                            "Write punchy posts under 120 words. "
                            "Always end with 3-5 relevant hashtags. "
                            "Always include one fan engagement question. "
                            "Never use emojis that may not render on all devices."
                        )
                    }]
                },
            },
            timeout=15,
        )
        data = resp.json()

        candidate = data.get("candidates", [{}])[0]
        finish_reason = candidate.get("finishReason", "")

        # Reject incomplete responses — these produce cut-off posts
        if finish_reason not in ("STOP", "stop", ""):
            logger.warning(
                "Gemini generation incomplete (finishReason=%s) - falling back to template.",
                finish_reason,
            )
            return None

        text = candidate["content"]["parts"][0]["text"]
        if not text or len(text.strip()) < 20:
            return None

        return text.strip()

    except KeyError as e:
        logger.warning("Gemini response missing key: %s - falling back to template.", e)
        return None
    except Exception as e:
        logger.warning("Gemini generation failed: %s - falling back to template.", e)
        return None


# ── Public caption generators ─────────────────────────────────

def generate_transfer_caption(player: str, from_club: str,
                               to_club: str, fee: str = "Undisclosed") -> str:
    gemini_key = (
        getattr(settings, "GEMINI_API_KEY", None)
        or __import__("os").getenv("GEMINI_API_KEY", "")
    )
    if gemini_key:
        # Short, explicit prompt — stays well under 180 token output
        prompt = (
            f"Football transfer post. "
            f"Player: {player}. From: {from_club}. To: {to_club}. Fee: {fee}. "
            f"Write a punchy 3-sentence caption with hashtags and one fan question. "
            f"Max 80 words total."
        )
        result = generate_with_gemini(prompt)
        if result:
            return result

    hashtags = build_hashtags("TRANSFER_ALERT", teams=[from_club, to_club])
    hashtags += " #TransferNews #Transfers"
    engagement = _engagement("TRANSFER_ALERT")
    return random.choice(TRANSFER_TEMPLATES).format(
        player=player, from_club=from_club or "Unknown",
        to_club=to_club or "Unknown", fee=fee,
        hashtags=hashtags, engagement=engagement,
    ).strip()


def generate_goal_caption(scorer: str, team: str, home_team: str,
                           away_team: str, home_score: int, away_score: int,
                           minute: int, competition: str,
                           assist: str = None) -> str:
    gemini_key = (
        getattr(settings, "GEMINI_API_KEY", None)
        or __import__("os").getenv("GEMINI_API_KEY", "")
    )
    if gemini_key:
        prompt = (
            f"Football goal caption. "
            f"Scorer: {scorer} ({team}). "
            f"Score: {home_team} {home_score}-{away_score} {away_team}. "
            f"Minute: {minute}'. Competition: {competition}. "
            f"Write 3 sentences max with hashtags and one fan question. Max 80 words."
        )
        result = generate_with_gemini(prompt)
        if result:
            return result

    hashtags = build_hashtags("GOAL", competition, [home_team, away_team])
    engagement = _engagement("GOAL")
    caption = random.choice(GOAL_TEMPLATES).format(
        scorer=scorer, team=team,
        home_team=home_team, away_team=away_team,
        home_score=home_score, away_score=away_score,
        minute=minute, competition=competition,
        hashtags=hashtags, engagement=engagement,
    )
    if assist:
        caption = caption.replace(hashtags, f"Assist: {assist}\n\n{hashtags}")
    return caption.strip()


def generate_fulltime_caption(home_team: str, away_team: str,
                               home_score: int, away_score: int,
                               competition: str, goals: list = None) -> str:
    gemini_key = (
        getattr(settings, "GEMINI_API_KEY", None)
        or __import__("os").getenv("GEMINI_API_KEY", "")
    )
    if gemini_key:
        prompt = (
            f"Football full-time result caption. "
            f"{home_team} {home_score}-{away_score} {away_team}. "
            f"Competition: {competition}. "
            f"Write 3 sentences with hashtags and ask fans to rate the match. Max 80 words."
        )
        result = generate_with_gemini(prompt)
        if result:
            return result

    hashtags = build_hashtags("FULLTIME", competition, [home_team, away_team])
    engagement = _engagement("FULLTIME")

    goals_summary = ""
    if goals:
        home_goals = [f"{g['player']} {g.get('minute','')}'" for g in goals if g.get("team") == "home"]
        away_goals = [f"{g['player']} {g.get('minute','')}'" for g in goals if g.get("team") == "away"]
        parts = []
        if home_goals:
            parts.append(f"{home_team}:\n" + "\n".join(home_goals))
        if away_goals:
            parts.append(f"{away_team}:\n" + "\n".join(away_goals))
        goals_summary = "\n\n".join(parts) + "\n\n" if parts else ""

    return random.choice(FULLTIME_TEMPLATES).format(
        home_team=home_team, away_team=away_team,
        home_score=home_score, away_score=away_score,
        competition=competition, goals_summary=goals_summary,
        hashtags=hashtags, engagement=engagement,
    ).strip()


def generate_matchday_caption(home_team: str, away_team: str,
                               kickoff_time: str, competition: str,
                               venue: str = "") -> str:
    hashtags = build_hashtags("MATCHDAY", competition, [home_team, away_team])
    engagement = _engagement("MATCHDAY")
    return random.choice(MATCHDAY_TEMPLATES).format(
        home_team=home_team, away_team=away_team,
        kickoff_time=kickoff_time, competition=competition,
        venue=venue or "TBA", hashtags=hashtags, engagement=engagement,
    ).strip()


def generate_fact_caption(fact_text: str) -> str:
    gemini_key = (
        getattr(settings, "GEMINI_API_KEY", None)
        or __import__("os").getenv("GEMINI_API_KEY", "")
    )
    if gemini_key:
        prompt = (
            f"Football fact social post. Fact: {fact_text}. "
            f"Write 2 sentences introducing it, add hashtags, ask fans if they knew. Max 80 words."
        )
        result = generate_with_gemini(prompt)
        if result:
            return result

    hashtags = build_hashtags("FOOTBALL_FACT")
    hashtags += " #FootballHistory #FootballTrivia"
    engagement = _engagement("FOOTBALL_FACT")
    return random.choice(FACT_TEMPLATES).format(
        fact_text=fact_text, hashtags=hashtags, engagement=engagement,
    ).strip()


def generate_league_table_caption(competition: str, leader: str, points: int) -> str:
    hashtags = build_hashtags("LEAGUE_TABLE", competition)
    engagement = _engagement("LEAGUE_TABLE")
    return (
        f"{competition.upper()} TABLE UPDATE\n\n"
        f"{leader} lead with {points} points!\n\n"
        f"{engagement}\n{hashtags}"
    ).strip()


def generate_top_scorers_caption(competition: str, leader: str, goals: int) -> str:
    hashtags = build_hashtags("TOP_SCORERS", competition)
    engagement = _engagement("TOP_SCORERS")
    return (
        f"{competition.upper()} TOP SCORERS\n\n"
        f"{leader} leads the race with {goals} goals!\n\n"
        f"{engagement}\n{hashtags}"
    ).strip()


def smart_caption(event_type: str, context: dict) -> str:
    dispatch = {
        "GOAL":           generate_goal_caption,
        "FULLTIME":       generate_fulltime_caption,
        "TRANSFER_ALERT": generate_transfer_caption,
        "MATCHDAY":       generate_matchday_caption,
        "FOOTBALL_FACT":  generate_fact_caption,
        "LEAGUE_TABLE":   generate_league_table_caption,
        "TOP_SCORERS":    generate_top_scorers_caption,
    }
    fn = dispatch.get(event_type)
    if fn:
        return fn(**context)
    return generate_fact_caption(str(context))
