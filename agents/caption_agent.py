"""
agents/caption_agent.py — Football Pulse AI
Generates captions, hashtags, and engagement questions.
Uses Google Gemini AI if GEMINI_API_KEY is set, otherwise falls back to templates.
"""

import random
import re
from typing import Optional

import settings
from utils.logger import setup_logger

logger = setup_logger("caption_agent")

# ─────────────────────────────────────────────────────────────────────────────
# Hashtag banks
# ─────────────────────────────────────────────────────────────────────────────

BASE_TAGS = ["#FootballPulse", "#Football", "#Soccer", "#FootballNews"]

COMPETITION_TAGS = {
    "Premier League":          ["#PremierLeague", "#EPL", "#BPLIVE"],
    "La Liga":                 ["#LaLiga", "#PrimeraDivision"],
    "UEFA Champions League":   ["#UCL", "#ChampionsLeague"],
    "UEFA Europa League":      ["#UEL", "#EuropaLeague"],
    "FIFA World Cup":          ["#WorldCup", "#FIFA", "#WorldCup2026"],
    "Bundesliga":              ["#Bundesliga", "#GermanFootball"],
    "Serie A":                 ["#SerieA", "#ItalianFootball"],
    "Ligue 1":                 ["#Ligue1", "#FrenchFootball"],
    "MLS":                     ["#MLS", "#MLSisBack"],
}

TEAM_TAG_OVERRIDES = {
    "Liverpool":    "#LFC",
    "Manchester City": "#MCFC",
    "Manchester United": "#MUFC",
    "Arsenal":      "#AFC",
    "Chelsea":      "#CFC",
    "Tottenham":    "#THFC",
    "Real Madrid":  "#RealMadrid",
    "Barcelona":    "#FCBarcelona",
    "Bayern Munich":"#FCBayern",
    "PSG":          "#PSG",
    "Juventus":     "#Juventus",
    "AC Milan":     "#ACMilan",
    "Inter Milan":  "#Inter",
    "Borussia Dortmund": "#BVB",
}

ENGAGEMENT_QUESTIONS = {
    "GOAL": [
        "Who was your Man of the Match?",
        "Was that a quality finish?",
        "What do you think of this goal? Drop your reaction below!",
        "Did you see that coming?",
    ],
    "FULLTIME": [
        "What are your player ratings for this match?",
        "Fair result? Tell us below!",
        "Who was the standout performer?",
        "Rate this match out of 10!",
    ],
    "TRANSFER_ALERT": [
        "Good signing or overpay?",
        "Will this transfer work out? Vote below!",
        "How many goals will they score this season?",
        "Smart business or panic buy?",
    ],
    "LEAGUE_TABLE": [
        "Who wins the title? Drop your prediction!",
        "Any surprises in the table?",
        "Who do you think gets relegated?",
    ],
    "TOP_SCORERS": [
        "Who wins the Golden Boot?",
        "Which striker impresses you most?",
    ],
    "MATCHDAY": [
        "Who are you backing today?",
        "Score prediction? Drop it below!",
        "Are you watching this one live?",
    ],
    "FOOTBALL_FACT": [
        "Did you know that? Share with a football fan!",
        "Mind blown? Drop a comment below!",
        "What is your favourite football fact?",
    ],
    "default": [
        "What do you think? Let us know below!",
        "Thoughts? Drop them in the comments!",
        "Share this with a fellow football fan!",
    ]
}

# ─────────────────────────────────────────────────────────────────────────────
# Template pools
# ─────────────────────────────────────────────────────────────────────────────

GOAL_TEMPLATES = [
    """\
GOAL! {scorer} finds the net for {team}!

{home_team} {home_score} - {away_score} {away_team}
{minute}' | {competition}

{engagement}
{hashtags}""",

    """\
{minute}' - {scorer} SCORES! {team} take the lead!

{home_team} {home_score} - {away_score} {away_team}
{competition}

{engagement}
{hashtags}""",

    """\
WHAT A GOAL! {scorer} with a stunning strike for {team}!

Score: {home_team} {home_score} - {away_score} {away_team}
{minute} minutes played | {competition}

{engagement}
{hashtags}""",
]

FULLTIME_TEMPLATES = [
    """\
FULL TIME!

{home_team} {home_score} - {away_score} {away_team}
{competition}

{goals_summary}
{engagement}
{hashtags}""",

    """\
IT'S ALL OVER!

{home_team} {home_score} - {away_score} {away_team}

The final whistle has blown in {competition}.

{goals_summary}
{engagement}
{hashtags}""",
]

TRANSFER_TEMPLATES = [
    """\
TRANSFER CONFIRMED!

{player} is officially heading to {to_club}!

From: {from_club}
To: {to_club}
Fee: {fee}

{engagement}
{hashtags}""",

    """\
DONE DEAL! {player} signs for {to_club}!

{from_club} to {to_club}
Fee: {fee}

{engagement}
{hashtags}""",
]

MATCHDAY_TEMPLATES = [
    """\
MATCHDAY!

{home_team} vs {away_team}
{kickoff_time} | {competition}
{venue}

{engagement}
{hashtags}""",

    """\
IT'S GAME DAY!

{home_team} vs {away_team}

Competition: {competition}
Kickoff: {kickoff_time}

{engagement}
{hashtags}""",
]

FACT_TEMPLATES = [
    """\
FOOTBALL FACT

{fact_text}

{engagement}
{hashtags}""",

    """\
DID YOU KNOW?

{fact_text}

{engagement}
{hashtags}""",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _team_hashtag(team_name: str) -> str:
    if team_name in TEAM_TAG_OVERRIDES:
        return TEAM_TAG_OVERRIDES[team_name]
    clean = re.sub(r"\s+", "", team_name)
    return f"#{clean}"


def build_hashtags(
    event_type: str,
    competition: str = None,
    teams: list[str] = None,
) -> str:
    tags = list(BASE_TAGS)
    if competition:
        tags += COMPETITION_TAGS.get(competition, [f"#{competition.replace(' ', '')}"])
    if teams:
        tags += [_team_hashtag(t) for t in teams if t]
    seen = set(); unique = []
    for t in tags:
        if t not in seen:
            seen.add(t); unique.append(t)
    return " ".join(unique[:12])


def _engagement(event_type: str) -> str:
    pool = ENGAGEMENT_QUESTIONS.get(event_type, ENGAGEMENT_QUESTIONS["default"])
    return random.choice(pool)


# ─────────────────────────────────────────────────────────────────────────────
# Google Gemini AI captions (free tier)
# ─────────────────────────────────────────────────────────────────────────────

def generate_with_gemini(prompt: str) -> Optional[str]:
    """
    Use Google Gemini free tier to generate captions if GEMINI_API_KEY is set.
    Free tier model: gemini-2.5-flash
    """
    gemini_key = getattr(settings, 'GEMINI_API_KEY', None) or __import__('os').getenv('GEMINI_API_KEY', '')
    if not gemini_key:
        return None
    try:
        import requests
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{
                        "text": (
                            "You are a football social media content creator for Football Pulse page. "
                            "Write punchy, engaging captions for football posts. "
                            "Always include relevant hashtags and a fan engagement question. "
                            "Keep responses under 200 words. No emojis that might not render correctly.\n\n"
                            + prompt
                        )
                    }]
                }],
                "generationConfig": {
                    "maxOutputTokens": 300,
                    "temperature": 0.85,
                }
            },
            timeout=20,
        )
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text.strip()
    except Exception as e:
        logger.warning("Gemini generation failed: %s - falling back to template.", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_goal_caption(
    scorer: str,
    team: str,
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    minute: int,
    competition: str,
    assist: str = None,
) -> str:
    # Try Gemini first
    gemini_key = getattr(settings, 'GEMINI_API_KEY', None) or __import__('os').getenv('GEMINI_API_KEY', '')
    if gemini_key:
        prompt = (
            f"Write a short hype football social media caption for a goal.\n"
            f"Scorer: {scorer}, Team: {team}, "
            f"Score: {home_team} {home_score} - {away_score} {away_team}, "
            f"Minute: {minute}', Competition: {competition}.\n"
            f"Include relevant hashtags and an engaging question for fans."
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


def generate_fulltime_caption(
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    competition: str,
    goals: list[dict] = None,
) -> str:
    gemini_key = getattr(settings, 'GEMINI_API_KEY', None) or __import__('os').getenv('GEMINI_API_KEY', '')
    if gemini_key:
        prompt = (
            f"Write a football full-time result caption.\n"
            f"{home_team} {home_score} - {away_score} {away_team} | {competition}.\n"
            f"Include hashtags and ask fans for their player ratings."
        )
        result = generate_with_gemini(prompt)
        if result:
            return result

    hashtags = build_hashtags("FULLTIME", competition, [home_team, away_team])
    engagement = _engagement("FULLTIME")

    if goals:
        home_goals = [f"{g['player']} {g.get('minute', '')}'" for g in goals if g.get("team") == "home"]
        away_goals = [f"{g['player']} {g.get('minute', '')}'" for g in goals if g.get("team") == "away"]
        parts = []
        if home_goals: parts.append(f"{home_team}:\n" + "\n".join(home_goals))
        if away_goals: parts.append(f"{away_team}:\n" + "\n".join(away_goals))
        goals_summary = "\n\n".join(parts)
    else:
        goals_summary = ""

    caption = random.choice(FULLTIME_TEMPLATES).format(
        home_team=home_team, away_team=away_team,
        home_score=home_score, away_score=away_score,
        competition=competition, goals_summary=goals_summary,
        hashtags=hashtags, engagement=engagement,
    )
    return caption.strip()


def generate_transfer_caption(
    player: str,
    from_club: str,
    to_club: str,
    fee: str = "Undisclosed",
) -> str:
    gemini_key = getattr(settings, 'GEMINI_API_KEY', None) or __import__('os').getenv('GEMINI_API_KEY', '')
    if gemini_key:
        prompt = (
            f"Write a football transfer announcement caption.\n"
            f"Player: {player}, From: {from_club}, To: {to_club}, Fee: {fee}.\n"
            f"Include hashtags and ask fans their opinion on the transfer."
        )
        result = generate_with_gemini(prompt)
        if result:
            return result

    hashtags = build_hashtags("TRANSFER_ALERT", teams=[from_club, to_club])
    hashtags += " #TransferNews #Transfers"
    engagement = _engagement("TRANSFER_ALERT")
    caption = random.choice(TRANSFER_TEMPLATES).format(
        player=player, from_club=from_club, to_club=to_club,
        fee=fee, hashtags=hashtags, engagement=engagement,
    )
    return caption.strip()


def generate_matchday_caption(
    home_team: str,
    away_team: str,
    kickoff_time: str,
    competition: str,
    venue: str = "",
) -> str:
    hashtags = build_hashtags("MATCHDAY", competition, [home_team, away_team])
    engagement = _engagement("MATCHDAY")
    caption = random.choice(MATCHDAY_TEMPLATES).format(
        home_team=home_team, away_team=away_team,
        kickoff_time=kickoff_time, competition=competition,
        venue=venue or "TBA", hashtags=hashtags, engagement=engagement,
    )
    return caption.strip()


def generate_fact_caption(fact_text: str) -> str:
    gemini_key = getattr(settings, 'GEMINI_API_KEY', None) or __import__('os').getenv('GEMINI_API_KEY', '')
    if gemini_key:
        prompt = (
            f"Write a fun football fact social media caption.\n"
            f"Fact: {fact_text}.\n"
            f"Include football hashtags and ask fans if they knew this fact."
        )
        result = generate_with_gemini(prompt)
        if result:
            return result

    hashtags = build_hashtags("FOOTBALL_FACT")
    hashtags += " #FootballHistory #FootballTrivia"
    engagement = _engagement("FOOTBALL_FACT")
    caption = random.choice(FACT_TEMPLATES).format(
        fact_text=fact_text, hashtags=hashtags, engagement=engagement,
    )
    return caption.strip()


def generate_league_table_caption(competition: str, leader: str, points: int) -> str:
    hashtags = build_hashtags("LEAGUE_TABLE", competition)
    engagement = _engagement("LEAGUE_TABLE")
    return f"""\
{competition.upper()} TABLE UPDATE

{leader} lead with {points} points!

{engagement}
{hashtags}""".strip()


def generate_top_scorers_caption(competition: str, leader: str, goals: int) -> str:
    hashtags = build_hashtags("TOP_SCORERS", competition)
    engagement = _engagement("TOP_SCORERS")
    return f"""\
{competition.upper()} TOP SCORERS

{leader} leads the race with {goals} goals!

{engagement}
{hashtags}""".strip()


def smart_caption(event_type: str, context: dict) -> str:
    dispatch = {
        "GOAL":            generate_goal_caption,
        "FULLTIME":        generate_fulltime_caption,
        "TRANSFER_ALERT":  generate_transfer_caption,
        "MATCHDAY":        generate_matchday_caption,
        "FOOTBALL_FACT":   generate_fact_caption,
        "LEAGUE_TABLE":    generate_league_table_caption,
        "TOP_SCORERS":     generate_top_scorers_caption,
    }
    fn = dispatch.get(event_type)
    if fn:
        return fn(**context)
    return generate_fact_caption(str(context))