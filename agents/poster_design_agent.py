"""
agents/poster_design_agent.py — Football Pulse AI
Generates professional football media graphics using Pillow.
All designs are mobile-first, bold, and inspired by 433 / Fabrizio Romano / ESPN FC.
"""

import io
import os
import textwrap
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import requests

import settings
from utils.logger import setup_logger

logger = setup_logger("poster_agent")

# ── Poster dimensions ─────────────────────────────────────────────────────
SIZES = {
    "square":   (1080, 1080),
    "portrait": (1080, 1350),
    "story":    (1080, 1920),
}

# ── Color palette (hex → RGB tuples) ──────────────────────────────────────
def hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

C = {k: hex_rgb(v) for k, v in settings.DESIGN.items()}
# Add alpha variants
C["bg_dark_a"]   = (*C["bg_dark"], 255)
C["overlay_60"]  = (0, 0, 0, 153)   # black 60%
C["overlay_80"]  = (0, 0, 0, 204)   # black 80%
C["accent_gold_dim"] = (180, 150, 0)


# ── Font loader ───────────────────────────────────────────────────────────

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a system font. Falls back to default if custom fonts not available."""
    font_paths_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        str(settings.FONTS_DIR / "bold.ttf"),
    ]
    font_paths_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        str(settings.FONTS_DIR / "regular.ttf"),
    ]
    paths = font_paths_bold if bold else font_paths_regular
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Image download helper ──────────────────────────────────────────────────

def _fetch_image(url: str, size: tuple = (200, 200)) -> Optional[Image.Image]:
    """Download and resize a remote image. Returns RGBA PIL Image or None."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10, stream=True)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        img = img.resize(size, Image.LANCZOS)
        return img
    except Exception as e:
        logger.warning("Image fetch failed (%s): %s", url, e)
        return None


# ── Gradient background ────────────────────────────────────────────────────

def _gradient_bg(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
    return img


# ── Diagonal accent stripe ──────────────────────────────────────────────────

def _add_accent_stripe(img: Image.Image, color: tuple) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    # Diagonal stripe from top-left region
    pts = [(0, h * 0.55), (w * 0.4, 0), (w * 0.45, 0), (0, h * 0.6)]
    draw.polygon(pts, fill=(*color, 40))
    return Image.alpha_composite(img, overlay)


# ── Branding bar ─────────────────────────────────────────────────────────────

def _draw_branding(draw: ImageDraw.Draw, w: int, y: int, size: int = 24):
    font = _load_font(size, bold=True)
    text = "⚽ FOOTBALL PULSE"
    draw.text((w // 2, y), text, font=font, fill=C["accent_gold"], anchor="mm")


# ── Divider line ─────────────────────────────────────────────────────────────

def _draw_divider(draw: ImageDraw.Draw, y: int, w: int, color: tuple = None, margin: int = 60):
    color = color or C["accent_gold"]
    draw.line([(margin, y), (w - margin, y)], fill=color, width=2)


# ═════════════════════════════════════════════════════════════════════════════
# POSTER TYPES
# ═════════════════════════════════════════════════════════════════════════════

def create_goal_alert(
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    scorer: str,
    minute: int,
    competition: str,
    assist: str = None,
    is_penalty: bool = False,
    home_logo_url: str = None,
    away_logo_url: str = None,
    player_photo_url: str = None,
    size_key: str = "portrait",
) -> Path:
    w, h = SIZES[size_key]
    img = _gradient_bg(w, h, C["bg_dark"], C["gradient_2"])
    img = _add_accent_stripe(img, C["accent_gold"])

    # Red glow panel at top
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_o  = ImageDraw.Draw(overlay)
    draw_o.rectangle([(0, 0), (w, h // 3)], fill=(*C["accent_red"], 30))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)

    # ── "GOAL!" headline ──────────────────────────────────────────────────
    goal_text = "GOAL! 🔥" if not is_penalty else "PENALTY GOAL! ⚽"
    font_huge = _load_font(130, bold=True)
    font_big  = _load_font(72,  bold=True)
    font_med  = _load_font(48,  bold=True)
    font_sm   = _load_font(36)
    font_xs   = _load_font(28)

    draw.text((w // 2, 110), goal_text, font=font_huge, fill=C["accent_gold"], anchor="mm")

    # ── Competition badge ──────────────────────────────────────────────────
    draw.text((w // 2, 215), competition.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    _draw_divider(draw, 245, w)

    # ── Team logos + scoreline ─────────────────────────────────────────────
    logo_y = 280
    logo_size = (120, 120)

    home_logo = _fetch_image(home_logo_url, logo_size)
    away_logo = _fetch_image(away_logo_url, logo_size)

    if home_logo:
        img.paste(home_logo, (100, logo_y), home_logo)
    if away_logo:
        img.paste(away_logo, (w - 220, logo_y), away_logo)

    # Score
    score_text = f"{home_score}  –  {away_score}"
    draw.text((w // 2, logo_y + 55), score_text, font=font_big, fill=C["text_primary"], anchor="mm")

    # Team names
    draw.text((160,     logo_y + 135), home_team.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    draw.text((w - 160, logo_y + 135), away_team.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")

    # Minute badge
    min_badge_x = w // 2
    min_badge_y = logo_y + 175
    badge_r = 35
    draw.ellipse(
        [(min_badge_x - badge_r, min_badge_y - badge_r),
         (min_badge_x + badge_r, min_badge_y + badge_r)],
        fill=C["accent_red"]
    )
    draw.text((min_badge_x, min_badge_y), f"{minute}'", font=_load_font(28, True), fill=C["text_primary"], anchor="mm")

    _draw_divider(draw, logo_y + 230, w)

    # ── Scorer section ──────────────────────────────────────────────────────
    scorer_y = logo_y + 265

    # Player photo
    player_img = _fetch_image(player_photo_url, (200, 200)) if player_photo_url else None
    if player_img:
        # Circle crop
        mask = Image.new("L", (200, 200), 0)
        ImageDraw.Draw(mask).ellipse([(0, 0), (200, 200)], fill=255)
        photo_circle = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        photo_circle.paste(player_img, mask=mask)
        img.paste(photo_circle, (w // 2 - 100, scorer_y), photo_circle)
        scorer_y += 215

    draw.text((w // 2, scorer_y),      "⚽  " + scorer.upper(), font=font_med, fill=C["text_primary"], anchor="mm")
    if assist:
        draw.text((w // 2, scorer_y + 60), f"Assist: {assist}", font=font_sm, fill=C["accent_gold"], anchor="mm")

    # ── Bottom branding ────────────────────────────────────────────────────
    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"goal_{home_team}_{away_team}_{minute}")


# ─────────────────────────────────────────────────────────────────────────────

def create_fulltime(
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    competition: str,
    goals: list[dict] = None,
    home_logo_url: str = None,
    away_logo_url: str = None,
    size_key: str = "portrait",
) -> Path:
    w, h = SIZES[size_key]
    img = _gradient_bg(w, h, C["bg_dark"], (18, 18, 40))

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_o  = ImageDraw.Draw(overlay)
    # Side accent bands
    draw_o.rectangle([(0, 0), (8, h)],       fill=(*C["accent_gold"], 200))
    draw_o.rectangle([(w - 8, 0), (w, h)],   fill=(*C["accent_gold"], 200))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)
    font_xl  = _load_font(90, True)
    font_big = _load_font(68, True)
    font_med = _load_font(44, True)
    font_sm  = _load_font(32)
    font_xs  = _load_font(26)

    # FT badge
    draw.text((w // 2, 90), "FULL TIME", font=font_xl, fill=C["text_primary"], anchor="mm")
    draw.text((w // 2, 160), competition.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    _draw_divider(draw, 190, w)

    # Logos + score
    logo_y = 220
    home_logo = _fetch_image(home_logo_url, (140, 140))
    away_logo = _fetch_image(away_logo_url, (140, 140))
    if home_logo: img.paste(home_logo, (80, logo_y), home_logo)
    if away_logo: img.paste(away_logo, (w - 220, logo_y), away_logo)

    score_text = f"{home_score}  –  {away_score}"
    draw.text((w // 2, logo_y + 65), score_text, font=font_big, fill=C["accent_gold"], anchor="mm")

    draw.text((150,     logo_y + 155), home_team.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    draw.text((w - 150, logo_y + 155), away_team.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")

    _draw_divider(draw, logo_y + 195, w)

    # Goals breakdown
    if goals:
        gy = logo_y + 225
        draw.text((w // 2, gy), "GOALS", font=_load_font(28, True), fill=C["accent_gold"], anchor="mm")
        gy += 45

        home_goals = [g for g in goals if g.get("team") == "home"]
        away_goals = [g for g in goals if g.get("team") == "away"]
        max_rows = max(len(home_goals), len(away_goals), 1)

        for i in range(max_rows):
            row_y = gy + i * 44
            if i < len(home_goals):
                g = home_goals[i]
                txt = f"⚽ {g.get('player', '')} {g.get('minute', '')}'"
                draw.text((120, row_y), txt, font=font_xs, fill=C["text_primary"])
            if i < len(away_goals):
                g = away_goals[i]
                txt = f"{g.get('minute', '')}' {g.get('player', '')} ⚽"
                tw = draw.textlength(txt, font=font_xs)
                draw.text((w - 120 - tw, row_y), txt, font=font_xs, fill=C["text_primary"])

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"fulltime_{home_team}_{away_team}")


# ─────────────────────────────────────────────────────────────────────────────

def create_matchday(
    home_team: str,
    away_team: str,
    kickoff_time: str,
    competition: str,
    venue: str = None,
    home_logo_url: str = None,
    away_logo_url: str = None,
    size_key: str = "square",
) -> Path:
    w, h = SIZES[size_key]
    img = _gradient_bg(w, h, (10, 10, 25), (25, 10, 50))

    # Star field effect
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    import random; rng = random.Random(42)
    draw_o = ImageDraw.Draw(overlay)
    for _ in range(120):
        x, y = rng.randint(0, w), rng.randint(0, h)
        r = rng.randint(1, 3)
        alpha = rng.randint(60, 180)
        draw_o.ellipse([(x-r, y-r), (x+r, y+r)], fill=(255, 255, 255, alpha))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)
    font_xl  = _load_font(80, True)
    font_big = _load_font(60, True)
    font_med = _load_font(44, True)
    font_sm  = _load_font(32)
    font_xs  = _load_font(26)

    draw.text((w // 2, 80), "MATCHDAY 🏟️", font=font_xl, fill=C["accent_gold"], anchor="mm")
    draw.text((w // 2, 155), competition.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    _draw_divider(draw, 185, w)

    # Logos + VS
    logo_y = 215
    home_logo = _fetch_image(home_logo_url, (160, 160))
    away_logo = _fetch_image(away_logo_url, (160, 160))
    if home_logo: img.paste(home_logo, (80, logo_y), home_logo)
    if away_logo: img.paste(away_logo, (w - 240, logo_y), away_logo)

    draw.text((w // 2, logo_y + 75), "VS", font=font_big, fill=C["text_primary"], anchor="mm")

    draw.text((160,     logo_y + 180), home_team.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    draw.text((w - 160, logo_y + 180), away_team.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")

    _draw_divider(draw, logo_y + 220, w)

    # Kickoff box
    box_y = logo_y + 250
    draw.rounded_rectangle([(w//2 - 180, box_y), (w//2 + 180, box_y + 80)], radius=12, fill=C["accent_red"])
    draw.text((w // 2, box_y + 40), f"🕐  {kickoff_time}", font=font_sm, fill=C["text_primary"], anchor="mm")

    if venue:
        draw.text((w // 2, box_y + 115), f"📍 {venue}", font=font_xs, fill=C["text_muted"], anchor="mm")

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"matchday_{home_team}_{away_team}")


# ─────────────────────────────────────────────────────────────────────────────

def create_league_table(
    competition: str,
    standings: list[dict],
    season: str = None,
    size_key: str = "portrait",
) -> Path:
    """
    standings: list of dicts with keys:
      position, team, played, won, drawn, lost, gd, points
    """
    w, h = SIZES[size_key]
    img = _gradient_bg(w, h, C["bg_dark"], C["gradient_2"])
    draw = ImageDraw.Draw(img)

    font_xl  = _load_font(70, True)
    font_med = _load_font(38, True)
    font_sm  = _load_font(28)
    font_xs  = _load_font(22)

    # Header
    draw.text((w // 2, 80), "LEAGUE TABLE", font=font_xl, fill=C["accent_gold"], anchor="mm")
    draw.text((w // 2, 140), competition.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    if season:
        draw.text((w // 2, 172), season, font=font_xs, fill=C["text_muted"], anchor="mm")
    _draw_divider(draw, 200, w, margin=40)

    # Column headers
    col_y = 225
    draw.text((55,    col_y), "#",   font=font_xs, fill=C["accent_gold"])
    draw.text((105,   col_y), "TEAM",font=font_xs, fill=C["accent_gold"])
    draw.text((640,   col_y), "P",   font=font_xs, fill=C["accent_gold"], anchor="mm")
    draw.text((715,   col_y), "W",   font=font_xs, fill=C["accent_gold"], anchor="mm")
    draw.text((790,   col_y), "D",   font=font_xs, fill=C["accent_gold"], anchor="mm")
    draw.text((865,   col_y), "L",   font=font_xs, fill=C["accent_gold"], anchor="mm")
    draw.text((940,   col_y), "GD",  font=font_xs, fill=C["accent_gold"], anchor="mm")
    draw.text((1020,  col_y), "PTS", font=font_xs, fill=C["accent_gold"], anchor="mm")

    _draw_divider(draw, col_y + 28, w, color=C["text_muted"], margin=40)

    row_h  = 56
    start_y = col_y + 45
    max_rows = min(len(standings), 16)  # show top 16

    for i, team in enumerate(standings[:max_rows]):
        ry = start_y + i * row_h
        pos = team.get("position", i + 1)

        # Highlight top 4 (green), relegation zone (red)
        if pos <= 4:
            bg_color = (*C["accent_green"], 30)
        elif pos >= max_rows - 2:
            bg_color = (*C["accent_red"], 25)
        else:
            bg_color = (*C["bg_card"], 60)

        overlay2 = Image.new("RGBA", (w, row_h), (0, 0, 0, 0))
        ImageDraw.Draw(overlay2).rectangle([(40, 0), (w - 40, row_h)], fill=bg_color)
        img.alpha_composite(overlay2, (0, ry))

        # Re-draw after composite
        draw = ImageDraw.Draw(img)

        name = team.get("team", "")[:18]
        pos_color = C["accent_gold"] if pos <= 4 else C["text_primary"]

        draw.text((55,    ry + row_h // 2), str(pos),                    font=font_xs, fill=pos_color, anchor="lm")
        draw.text((105,   ry + row_h // 2), name,                         font=font_sm, fill=C["text_primary"], anchor="lm")
        draw.text((640,   ry + row_h // 2), str(team.get("played", 0)),  font=font_xs, fill=C["text_muted"],   anchor="mm")
        draw.text((715,   ry + row_h // 2), str(team.get("won", 0)),     font=font_xs, fill=C["text_muted"],   anchor="mm")
        draw.text((790,   ry + row_h // 2), str(team.get("drawn", 0)),   font=font_xs, fill=C["text_muted"],   anchor="mm")
        draw.text((865,   ry + row_h // 2), str(team.get("lost", 0)),    font=font_xs, fill=C["text_muted"],   anchor="mm")
        gd = team.get("gd", 0)
        gd_str = f"+{gd}" if gd > 0 else str(gd)
        draw.text((940,   ry + row_h // 2), gd_str,                       font=font_xs, fill=C["accent_green"] if gd > 0 else C["accent_red"], anchor="mm")
        draw.text((1020,  ry + row_h // 2), str(team.get("points", 0)),  font=font_med, fill=C["text_primary"], anchor="mm")

        if i < max_rows - 1:
            _draw_divider(draw, ry + row_h - 1, w, color=(60, 60, 80), margin=40)

    _draw_branding(draw, w, h - 50)

    return _save(img, f"table_{competition.replace(' ', '_')}")


# ─────────────────────────────────────────────────────────────────────────────

def create_top_scorers(
    competition: str,
    scorers: list[dict],
    size_key: str = "portrait",
) -> Path:
    """
    scorers: list of dicts: player_name, team, goals, assists
    """
    w, h = SIZES[size_key]
    img = _gradient_bg(w, h, (10, 5, 20), (20, 10, 35))
    draw = ImageDraw.Draw(img)

    font_xl  = _load_font(70, True)
    font_med = _load_font(40, True)
    font_sm  = _load_font(30)
    font_xs  = _load_font(24)

    draw.text((w // 2, 80), "TOP SCORERS ⚽", font=font_xl, fill=C["accent_gold"], anchor="mm")
    draw.text((w // 2, 148), competition.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    _draw_divider(draw, 178, w)

    row_h   = 90
    start_y = 200

    for i, s in enumerate(scorers[:10]):
        ry = start_y + i * row_h
        is_top = (i == 0)
        bg = (*C["accent_gold"], 25) if is_top else (*C["bg_card"], 50)

        ov = Image.new("RGBA", (w, row_h - 4), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle([(40, 0), (w - 40, row_h - 4)], radius=8, fill=bg)
        img.alpha_composite(ov, (0, ry + 2))
        draw = ImageDraw.Draw(img)

        # Rank
        rank_color = C["accent_gold"] if is_top else C["text_muted"]
        draw.text((80, ry + row_h // 2), f"{i+1}", font=font_med, fill=rank_color, anchor="mm")

        # Name + team
        name_color = C["accent_gold"] if is_top else C["text_primary"]
        draw.text((130, ry + row_h // 2 - 12), s.get("player_name", "")[:22], font=font_sm, fill=name_color, anchor="lm")
        draw.text((130, ry + row_h // 2 + 18), s.get("team", ""),            font=font_xs, fill=C["text_muted"], anchor="lm")

        # Goals
        draw.text((w - 90, ry + row_h // 2), str(s.get("goals", 0)), font=font_xl, fill=C["text_primary"], anchor="mm")
        draw.text((w - 90, ry + row_h // 2 + 30), "goals", font=font_xs, fill=C["text_muted"], anchor="mm")

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"scorers_{competition.replace(' ', '_')}")


# ─────────────────────────────────────────────────────────────────────────────

def create_transfer_alert(
    player_name: str,
    from_club: str,
    to_club: str,
    fee: str = "Undisclosed",
    player_photo_url: str = None,
    from_logo_url: str = None,
    to_logo_url: str = None,
    size_key: str = "portrait",
) -> Path:
    w, h = SIZES[size_key]
    img = _gradient_bg(w, h, (5, 5, 15), (15, 5, 30))

    # Green neon glow overlay
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(ov).ellipse([(-100, -100), (w + 100, h // 2)], fill=(*C["accent_green"], 15))
    img = Image.alpha_composite(img, ov)

    draw = ImageDraw.Draw(img)
    font_xl  = _load_font(80, True)
    font_big = _load_font(60, True)
    font_med = _load_font(44, True)
    font_sm  = _load_font(32)
    font_xs  = _load_font(26)

    draw.text((w // 2, 85), "🚨 TRANSFER ALERT", font=font_xl, fill=C["accent_green"], anchor="mm")
    _draw_divider(draw, 130, w)

    # Player photo
    photo_y = 150
    player_img = _fetch_image(player_photo_url, (260, 260)) if player_photo_url else None
    if player_img:
        mask = Image.new("L", (260, 260), 0)
        ImageDraw.Draw(mask).ellipse([(0, 0), (260, 260)], fill=255)
        circle = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
        circle.paste(player_img, mask=mask)
        # Gold ring
        ring_img = Image.new("RGBA", (280, 280), (0, 0, 0, 0))
        ImageDraw.Draw(ring_img).ellipse([(0, 0), (280, 280)], fill=C["accent_gold"])
        ring_img.paste(circle, (10, 10), circle)
        img.paste(ring_img, (w // 2 - 140, photo_y), ring_img)
        photo_y += 295

    draw = ImageDraw.Draw(img)
    draw.text((w // 2, photo_y), player_name.upper(), font=font_big, fill=C["text_primary"], anchor="mm")
    photo_y += 70

    # From → To with logos
    logo_y = photo_y
    from_logo = _fetch_image(from_logo_url, (110, 110))
    to_logo   = _fetch_image(to_logo_url,   (110, 110))

    if from_logo: img.paste(from_logo, (120, logo_y), from_logo)
    draw = ImageDraw.Draw(img)
    draw.text((w // 2, logo_y + 50), "→", font=font_big, fill=C["accent_gold"], anchor="mm")
    if to_logo: img.paste(to_logo, (w - 230, logo_y), to_logo)

    logo_y += 130
    draw = ImageDraw.Draw(img)
    draw.text((175,     logo_y), from_club, font=font_xs, fill=C["text_muted"], anchor="mm")
    draw.text((w - 175, logo_y), to_club,   font=font_xs, fill=C["accent_green"], anchor="mm")

    # Fee
    logo_y += 55
    draw.rounded_rectangle([(w//2 - 160, logo_y), (w//2 + 160, logo_y + 60)], radius=10, fill=C["accent_gold"])
    draw.text((w // 2, logo_y + 30), f"FEE: {fee}", font=font_sm, fill=C["bg_dark"], anchor="mm")

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"transfer_{player_name.replace(' ', '_')}")


# ─────────────────────────────────────────────────────────────────────────────

def create_football_fact(
    fact_text: str,
    category: str = "FOOTBALL FACT",
    emoji: str = "⚽",
    size_key: str = "square",
) -> Path:
    w, h = SIZES[size_key]
    img = _gradient_bg(w, h, (8, 8, 18), (20, 8, 40))
    img = _add_accent_stripe(img, C["accent_blue"])

    draw = ImageDraw.Draw(img)
    font_xl  = _load_font(75, True)
    font_med = _load_font(48)
    font_sm  = _load_font(36)

    # Category
    draw.text((w // 2, 100), f"{emoji} {category}", font=font_xl, fill=C["accent_gold"], anchor="mm")
    _draw_divider(draw, 150, w)

    # Quotation mark decoration
    #draw.text((60, 180), "\u201c", font=_load_font(180, True), fill=(*C["accent_blue"], 80))

    # Wrap fact text
    lines = textwrap.wrap(fact_text, width=28)
    text_y = 270
    for line in lines:
        draw.text((w // 2, text_y), line, font=font_sm, fill=C["text_primary"], anchor="mm")
        text_y += 52

    #draw.text((w - 60, text_y + 20), "\u201d", font=_load_font(180, True), fill=(*C["accent_blue"], 80), anchor="rm")

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"fact_{category.replace(' ', '_')}_{int(datetime.now().timestamp())}")


# ─────────────────────────────────────────────────────────────────────────────

def create_todays_fixtures(
    fixtures: list[dict],
    date_label: str = "TODAY",
    size_key: str = "portrait",
) -> Path:
    """
    fixtures: list of dicts: home_team, away_team, kickoff_time, competition
    """
    w, h = SIZES[size_key]
    img = _gradient_bg(w, h, C["bg_dark"], (15, 15, 30))
    draw = ImageDraw.Draw(img)

    font_xl  = _load_font(70, True)
    font_med = _load_font(38, True)
    font_sm  = _load_font(28)
    font_xs  = _load_font(22)

    draw.text((w // 2, 80), f"📅 {date_label}'S FIXTURES", font=font_xl, fill=C["accent_gold"], anchor="mm")
    _draw_divider(draw, 125, w)

    row_h   = 100
    start_y = 145

    for i, fix in enumerate(fixtures[:10]):
        ry = start_y + i * row_h
        bg = (*C["bg_card"], 120) if i % 2 == 0 else (0, 0, 0, 0)

        ov = Image.new("RGBA", (w, row_h - 6), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rectangle([(40, 0), (w - 40, row_h - 6)], fill=bg)
        img.alpha_composite(ov, (0, ry + 3))
        draw = ImageDraw.Draw(img)

        home = fix.get("home_team", "")[:16]
        away = fix.get("away_team", "")[:16]
        time = fix.get("kickoff_time", "TBC")
        comp = fix.get("competition", "")[:20]

        draw.text((90,    ry + row_h // 2 - 10), home, font=font_sm, fill=C["text_primary"], anchor="lm")
        draw.text((w//2,  ry + row_h // 2 - 10), time, font=font_med, fill=C["accent_gold"], anchor="mm")
        tw = draw.textlength(away, font=font_sm)
        draw.text((w - 90, ry + row_h // 2 - 10), away, font=font_sm, fill=C["text_primary"], anchor="rm")
        draw.text((w//2,  ry + row_h // 2 + 22), comp, font=font_xs, fill=C["text_muted"], anchor="mm")

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"fixtures_{date_label.replace(' ', '_')}")


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _save(img: Image.Image, name: str) -> Path:
    """Convert to RGB and save as JPEG in poster output dir."""
    final = Image.new("RGB", img.size, (0, 0, 0))
    if img.mode == "RGBA":
        final.paste(img, mask=img.split()[3])
    else:
        final = img.convert("RGB")

    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = settings.POSTER_DIR / f"{name}_{ts}.jpg"
    final.save(str(path), "JPEG", quality=95, optimize=True)
    logger.info("Poster saved: %s", path)
    return path
