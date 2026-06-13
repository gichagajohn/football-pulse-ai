#!/usr/bin/env python3
"""
test_posters.py — Football Pulse AI
Generate sample posters locally to verify design before deploying.
Run: python test_posters.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from agents import poster_design_agent as poster

print("Generating test posters…\n")

# 1. Goal Alert
p = poster.create_goal_alert(
    home_team   = "Liverpool",
    away_team   = "Arsenal",
    home_score  = 2,
    away_score  = 1,
    scorer      = "Mohamed Salah",
    minute      = 87,
    competition = "Premier League",
    assist      = "Trent Alexander-Arnold",
)
print(f"✅ Goal Alert:    {p}")

# 2. Full Time
p = poster.create_fulltime(
    home_team  = "Manchester City",
    away_team  = "Chelsea",
    home_score = 3,
    away_score = 1,
    competition= "Premier League",
    goals      = [
        {"team": "home", "player": "Haaland",   "minute": 12},
        {"team": "home", "player": "De Bruyne",  "minute": 44},
        {"team": "away", "player": "Palmer",     "minute": 61},
        {"team": "home", "player": "Foden",      "minute": 78},
    ],
)
print(f"✅ Full Time:     {p}")

# 3. Matchday
p = poster.create_matchday(
    home_team   = "Real Madrid",
    away_team   = "Barcelona",
    kickoff_time= "20:45",
    competition = "La Liga",
    venue       = "Santiago Bernabéu",
)
print(f"✅ Matchday:      {p}")

# 4. League Table
p = poster.create_league_table(
    competition = "Premier League",
    standings   = [
        {"position": 1, "team": "Manchester City", "played": 30, "won": 22, "drawn": 4, "lost": 4, "gd": 52, "points": 70},
        {"position": 2, "team": "Arsenal",         "played": 30, "won": 20, "drawn": 5, "lost": 5, "gd": 38, "points": 65},
        {"position": 3, "team": "Liverpool",        "played": 30, "won": 19, "drawn": 6, "lost": 5, "gd": 40, "points": 63},
        {"position": 4, "team": "Aston Villa",      "played": 30, "won": 18, "drawn": 4, "lost": 8, "gd": 22, "points": 58},
        {"position": 5, "team": "Tottenham",        "played": 30, "won": 15, "drawn": 5, "lost":10, "gd": 12, "points": 50},
        {"position": 6, "team": "Chelsea",          "played": 30, "won": 13, "drawn": 8, "lost": 9, "gd":  8, "points": 47},
        {"position": 7, "team": "Newcastle",        "played": 30, "won": 13, "drawn": 6, "lost":11, "gd":  5, "points": 45},
        {"position": 8, "team": "Man United",       "played": 30, "won": 11, "drawn": 7, "lost":12, "gd": -8, "points": 40},
        {"position": 16,"team": "Burnley",          "played": 30, "won":  5, "drawn": 5, "lost":20, "gd":-38, "points": 20},
        {"position": 17,"team": "Luton",            "played": 30, "won":  5, "drawn": 4, "lost":21, "gd":-42, "points": 19},
        {"position": 18,"team": "Sheffield Utd",    "played": 30, "won":  3, "drawn": 4, "lost":23, "gd":-58, "points": 13},
    ],
    season      = "2023/24",
)
print(f"✅ League Table: {p}")

# 5. Top Scorers
p = poster.create_top_scorers(
    competition = "Premier League",
    scorers     = [
        {"player_name": "Erling Haaland",    "team": "Man City",  "goals": 27, "assists": 5},
        {"player_name": "Ollie Watkins",     "team": "Aston Villa","goals": 19, "assists": 8},
        {"player_name": "Cole Palmer",       "team": "Chelsea",   "goals": 18, "assists": 9},
        {"player_name": "Alexander Isak",    "team": "Newcastle", "goals": 17, "assists": 2},
        {"player_name": "Mohamed Salah",     "team": "Liverpool", "goals": 15, "assists": 9},
    ],
)
print(f"✅ Top Scorers:  {p}")

# 6. Transfer Alert
p = poster.create_transfer_alert(
    player_name = "Kylian Mbappé",
    from_club   = "PSG",
    to_club     = "Real Madrid",
    fee         = "Free Transfer",
)
print(f"✅ Transfer:     {p}")

# 7. Football Fact
p = poster.create_football_fact(
    "Pelé is the only player to have won three FIFA World Cups, achieving this feat in 1958, 1962, and 1970 with Brazil."
)
print(f"✅ Fact:         {p}")

# 8. Today's Fixtures
p = poster.create_todays_fixtures([
    {"home_team": "Liverpool",  "away_team": "Man City", "kickoff_time": "16:30", "competition": "Premier League"},
    {"home_team": "Real Madrid","away_team": "Bayern",   "kickoff_time": "21:00", "competition": "UCL"},
    {"home_team": "Barcelona",  "away_team": "PSG",      "kickoff_time": "21:00", "competition": "UCL"},
    {"home_team": "Arsenal",    "away_team": "Chelsea",  "kickoff_time": "12:30", "competition": "Premier League"},
])
print(f"✅ Fixtures:     {p}")

print("\n🎉 All posters generated! Check the output/posters/ directory.")

print("\n--- Extra poster types ---\n")

from agents.extra_posters import create_starting_xi, create_record_broken, create_half_time

# Starting XI
p = create_starting_xi(
    team_name="Liverpool",
    competition="Premier League",
    formation="4-3-3",
    opponent="Arsenal",
    players=[
        {"name": "Alisson",    "number": 1,  "position": "GK"},
        {"name": "Alexander-Arnold","number":66,"position":"RB"},
        {"name": "Konate",     "number": 5,  "position": "CB"},
        {"name": "Van Dijk",   "number": 4,  "position": "CB"},
        {"name": "Robertson",  "number": 26, "position": "LB"},
        {"name": "Mac Allister","number":10, "position": "CM"},
        {"name": "Szoboszlai", "number": 8,  "position": "CM"},
        {"name": "Jones",      "number": 17, "position": "CM"},
        {"name": "Salah",      "number": 11, "position": "RW"},
        {"name": "Nunez",      "number": 9,  "position": "ST"},
        {"name": "Diaz",       "number": 23, "position": "LW"},
    ],
)
print(f"✅ Starting XI:   {p}")

# Record Broken
p = create_record_broken(
    player_name="Cristiano Ronaldo",
    record_text="Most international goals ever — 130 goals",
    previous_holder="Ali Daei (109 goals)",
    competition="International Football",
)
print(f"✅ Record Broken: {p}")

# Half Time
p = create_half_time(
    home_team="Man City",
    away_team="Real Madrid",
    home_score=1,
    away_score=0,
    competition="UEFA Champions League",
)
print(f"✅ Half Time:     {p}")

print("\n🎉 All extra posters generated!")
