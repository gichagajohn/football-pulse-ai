"""
agents/poster_design_agent.py — Football Pulse AI
Generates professional football media graphics using Pillow.
All designs are mobile-first, bold, and inspired by 433 / Fabrizio Romano / ESPN FC.
"""

import io
import os
import re
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
C["bg_dark_a"]       = (*C["bg_dark"], 255)
C["overlay_60"]      = (0, 0, 0, 153)
C["overlay_80"]      = (0, 0, 0, 204)
C["accent_gold_dim"] = (180, 150, 0)


# ── Emoji stripper ────────────────────────────────────────────────────────
# PIL system fonts can't render emoji — strip them before drawing on poster.
# Emoji still appear in the Facebook caption text where they render fine.

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002500-\U00002BEF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001f926-\U0001f937"
    "\U00010000-\U0010ffff"
    "\u2640-\u2642"
    "\u2600-\u2B55"
    "\u200d\u23cf\u23e9\u231a\ufe0f\u3030"
    "]+",
    flags=re.UNICODE,
)

def _clean(text: str) -> str:
    """Strip emoji and tidy whitespace for poster text rendering."""
    return re.sub(r"\s+", " ", _EMOJI_RE.sub("", text)).strip()


# ── Font loader ───────────────────────────────────────────────────────────

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
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


# ── Diagonal accent stripe ────────────────────────────────────────────────

def _add_accent_stripe(img: Image.Image, color: tuple) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    pts = [(0, h * 0.55), (w * 0.4, 0), (w * 0.45, 0), (0, h * 0.6)]
    draw.polygon(pts, fill=(*color, 40))
    return Image.alpha_composite(img, overlay)


# ── Branding bar ──────────────────────────────────────────────────────────

def _draw_branding(draw: ImageDraw.Draw, w: int, y: int, size: int = 24):
    font = _load_font(size, bold=True)
    draw.text((w // 2, y), "FOOTBALL PULSE", font=font, fill=C["accent_gold"], anchor="mm")


# ── Divider line ──────────────────────────────────────────────────────────

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

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle([(0, 0), (w, h // 3)], fill=(*C["accent_red"], 30))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)

    goal_text = "PENALTY GOAL!" if is_penalty else "GOAL!"
    font_huge = _load_font(130, bold=True)
    font_big  = _load_font(72,  bold=True)
    font_med  = _load_font(48,  bold=True)
    font_sm   = _load_font(36)
    font_xs   = _load_font(28)

    draw.text((w // 2, 110), goal_text, font=font_huge, fill=C["accent_gold"], anchor="mm")
    draw.text((w // 2, 215), _clean(competition).upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    _draw_divider(draw, 245, w)

    logo_y    = 280
    logo_size = (120, 120)
    home_logo = _fetch_image(home_logo_url, logo_size)
    away_logo = _fetch_image(away_logo_url, logo_size)
    if home_logo: img.paste(home_logo, (100, logo_y), home_logo)
    if away_logo: img.paste(away_logo, (w - 220, logo_y), away_logo)

    draw.text((w // 2, logo_y + 55), f"{home_score}  -  {away_score}", font=font_big, fill=C["text_primary"], anchor="mm")
    draw.text((160,     logo_y + 135), _clean(home_team).upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    draw.text((w - 160, logo_y + 135), _clean(away_team).upper(), font=font_xs, fill=C["text_muted"], anchor="mm")

    badge_r = 35
    bx, by  = w // 2, logo_y + 175
    draw.ellipse([(bx - badge_r, by - badge_r), (bx + badge_r, by + badge_r)], fill=C["accent_red"])
    draw.text((bx, by), f"{minute}'", font=_load_font(28, True), fill=C["text_primary"], anchor="mm")

    _draw_divider(draw, logo_y + 230, w)
    scorer_y = logo_y + 265

    player_img = _fetch_image(player_photo_url, (200, 200)) if player_photo_url else None
    if player_img:
        mask = Image.new("L", (200, 200), 0)
        ImageDraw.Draw(mask).ellipse([(0, 0), (200, 200)], fill=255)
        photo_circle = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        photo_circle.paste(player_img, mask=mask)
        img.paste(photo_circle, (w // 2 - 100, scorer_y), photo_circle)
        scorer_y += 215

    if scorer:
        draw.text((w // 2, scorer_y), _clean(scorer).upper(), font=font_med, fill=C["text_primary"], anchor="mm")
    if assist:
        draw.text((w // 2, scorer_y + 60), f"Assist: {_clean(assist)}", font=font_sm, fill=C["accent_gold"], anchor="mm")

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
    draw_o.rectangle([(0, 0), (8, h)],     fill=(*C["accent_gold"], 200))
    draw_o.rectangle([(w - 8, 0), (w, h)], fill=(*C["accent_gold"], 200))
    img = Image.alpha_composite(img, overlay)

    draw    = ImageDraw.Draw(img)
    font_xl  = _load_font(90, True)
    font_big = _load_font(68, True)
    font_med = _load_font(44, True)
    font_sm  = _load_font(32)
    font_xs  = _load_font(26)

    draw.text((w // 2, 90),  "FULL TIME",                      font=font_xl, fill=C["text_primary"], anchor="mm")
    draw.text((w // 2, 160), _clean(competition).upper(),       font=font_xs, fill=C["text_muted"],   anchor="mm")
    _draw_divider(draw, 190, w)

    logo_y    = 220
    home_logo = _fetch_image(home_logo_url, (140, 140))
    away_logo = _fetch_image(away_logo_url, (140, 140))
    if home_logo: img.paste(home_logo, (80, logo_y), home_logo)
    if away_logo: img.paste(away_logo, (w - 220, logo_y), away_logo)

    draw.text((w // 2, logo_y + 65),  f"{home_score}  -  {away_score}",  font=font_big, fill=C["accent_gold"], anchor="mm")
    draw.text((150,     logo_y + 155), _clean(home_team).upper(),          font=font_xs,  fill=C["text_muted"],  anchor="mm")
    draw.text((w - 150, logo_y + 155), _clean(away_team).upper(),          font=font_xs,  fill=C["text_muted"],  anchor="mm")

    _draw_divider(draw, logo_y + 195, w)

    if goals:
        gy = logo_y + 225
        draw.text((w // 2, gy), "GOALS", font=_load_font(28, True), fill=C["accent_gold"], anchor="mm")
        gy += 45
        home_goals = [g for g in goals if g.get("team") == "home"]
        away_goals = [g for g in goals if g.get("team") == "away"]
        for i in range(max(len(home_goals), len(away_goals))):
            row_y = gy + i * 44
            if i < len(home_goals):
                g   = home_goals[i]
                txt = f"{_clean(g.get('player',''))} {g.get('minute','')}'"
                draw.text((120, row_y), txt, font=font_xs, fill=C["text_primary"])
            if i < len(away_goals):
                g   = away_goals[i]
                txt = f"{g.get('minute','')}' {_clean(g.get('player',''))}"
                tw  = draw.textlength(txt, font=font_xs)
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

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    import random; rng = random.Random(42)
    draw_o = ImageDraw.Draw(overlay)
    for _ in range(120):
        x, y  = rng.randint(0, w), rng.randint(0, h)
        r     = rng.randint(1, 3)
        alpha = rng.randint(60, 180)
        draw_o.ellipse([(x-r, y-r), (x+r, y+r)], fill=(255, 255, 255, alpha))
    img = Image.alpha_composite(img, overlay)

    draw     = ImageDraw.Draw(img)
    font_xl  = _load_font(80, True)
    font_big = _load_font(60, True)
    font_xs  = _load_font(26)
    font_sm  = _load_font(32)

    draw.text((w // 2, 80),  "MATCHDAY",                      font=font_xl, fill=C["accent_gold"], anchor="mm")
    draw.text((w // 2, 155), _clean(competition).upper(),      font=font_xs, fill=C["text_muted"],  anchor="mm")
    _draw_divider(draw, 185, w)

    logo_y    = 215
    home_logo = _fetch_image(home_logo_url, (160, 160))
    away_logo = _fetch_image(away_logo_url, (160, 160))
    if home_logo: img.paste(home_logo, (80, logo_y), home_logo)
    if away_logo: img.paste(away_logo, (w - 240, logo_y), away_logo)

    draw.text((w // 2, logo_y + 75),  "VS",                          font=font_big, fill=C["text_primary"], anchor="mm")
    draw.text((160,     logo_y + 180), _clean(home_team).upper(),     font=font_xs,  fill=C["text_muted"],   anchor="mm")
    draw.text((w - 160, logo_y + 180), _clean(away_team).upper(),     font=font_xs,  fill=C["text_muted"],   anchor="mm")

    _draw_divider(draw, logo_y + 220, w)

    box_y = logo_y + 250
    draw.rounded_rectangle([(w//2 - 180, box_y), (w//2 + 180, box_y + 80)], radius=12, fill=C["accent_red"])
    draw.text((w // 2, box_y + 40), _clean(kickoff_time), font=font_sm, fill=C["text_primary"], anchor="mm")

    if venue:
        draw.text((w // 2, box_y + 115), _clean(venue), font=font_xs, fill=C["text_muted"], anchor="mm")

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
    w, h = SIZES[size_key]
    img  = _gradient_bg(w, h, C["bg_dark"], C["gradient_2"])
    draw = ImageDraw.Draw(img)

    font_xl  = _load_font(70, True)
    font_med = _load_font(38, True)
    font_sm  = _load_font(28)
    font_xs  = _load_font(22)

    draw.text((w // 2, 80),  "LEAGUE TABLE",                  font=font_xl, fill=C["accent_gold"], anchor="mm")
    draw.text((w // 2, 140), _clean(competition).upper(),      font=font_xs, fill=C["text_muted"],  anchor="mm")
    if season:
        draw.text((w // 2, 172), season, font=font_xs, fill=C["text_muted"], anchor="mm")
    _draw_divider(draw, 200, w, margin=40)

    col_y = 225
    for x, label in [(55, "#"), (105, "TEAM"), (640, "P"), (715, "W"), (790, "D"), (865, "L"), (940, "GD"), (1020, "PTS")]:
        anchor = "lm" if x < 200 else "mm"
        draw.text((x, col_y), label, font=font_xs, fill=C["accent_gold"], anchor=anchor)

    _draw_divider(draw, col_y + 28, w, color=C["text_muted"], margin=40)

    row_h   = 56
    start_y = col_y + 45
    max_rows = min(len(standings), 16)

    for i, team in enumerate(standings[:max_rows]):
        ry  = start_y + i * row_h
        pos = team.get("position", i + 1)

        bg_color = (*C["accent_green"], 30) if pos <= 4 else ((*C["accent_red"], 25) if pos >= max_rows - 2 else (*C["bg_card"], 60))
        ov2 = Image.new("RGBA", (w, row_h), (0, 0, 0, 0))
        ImageDraw.Draw(ov2).rectangle([(40, 0), (w - 40, row_h)], fill=bg_color)
        img.alpha_composite(ov2, (0, ry))
        draw = ImageDraw.Draw(img)

        name      = _clean(team.get("team", ""))[:18]
        pos_color = C["accent_gold"] if pos <= 4 else C["text_primary"]
        gd        = team.get("gd", 0)
        gd_str    = f"+{gd}" if gd > 0 else str(gd)

        draw.text((55,   ry + row_h // 2), str(pos),                   font=font_xs,  fill=pos_color,           anchor="lm")
        draw.text((105,  ry + row_h // 2), name,                        font=font_sm,  fill=C["text_primary"],   anchor="lm")
        draw.text((640,  ry + row_h // 2), str(team.get("played", 0)), font=font_xs,  fill=C["text_muted"],     anchor="mm")
        draw.text((715,  ry + row_h // 2), str(team.get("won", 0)),    font=font_xs,  fill=C["text_muted"],     anchor="mm")
        draw.text((790,  ry + row_h // 2), str(team.get("drawn", 0)),  font=font_xs,  fill=C["text_muted"],     anchor="mm")
        draw.text((865,  ry + row_h // 2), str(team.get("lost", 0)),   font=font_xs,  fill=C["text_muted"],     anchor="mm")
        draw.text((940,  ry + row_h // 2), gd_str,                      font=font_xs,  fill=C["accent_green"] if gd > 0 else C["accent_red"], anchor="mm")
        draw.text((1020, ry + row_h // 2), str(team.get("points", 0)), font=font_med, fill=C["text_primary"],   anchor="mm")

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
    w, h = SIZES[size_key]
    img  = _gradient_bg(w, h, (10, 5, 20), (20, 10, 35))
    draw = ImageDraw.Draw(img)

    font_xl  = _load_font(70, True)
    font_med = _load_font(40, True)
    font_sm  = _load_font(30)
    font_xs  = _load_font(24)

    draw.text((w // 2, 80),  "TOP SCORERS",               font=font_xl, fill=C["accent_gold"], anchor="mm")
    draw.text((w // 2, 148), _clean(competition).upper(),  font=font_xs, fill=C["text_muted"],  anchor="mm")
    _draw_divider(draw, 178, w)

    row_h   = 90
    start_y = 200

    for i, s in enumerate(scorers[:10]):
        ry     = start_y + i * row_h
        is_top = (i == 0)
        bg     = (*C["accent_gold"], 25) if is_top else (*C["bg_card"], 50)

        ov = Image.new("RGBA", (w, row_h - 4), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle([(40, 0), (w - 40, row_h - 4)], radius=8, fill=bg)
        img.alpha_composite(ov, (0, ry + 2))
        draw = ImageDraw.Draw(img)

        rank_color = C["accent_gold"] if is_top else C["text_muted"]
        name_color = C["accent_gold"] if is_top else C["text_primary"]
        draw.text((80,  ry + row_h // 2),      f"{i+1}",                              font=font_med, fill=rank_color,        anchor="mm")
        draw.text((130, ry + row_h // 2 - 12), _clean(s.get("player_name",""))[:22],  font=font_sm,  fill=name_color,        anchor="lm")
        draw.text((130, ry + row_h // 2 + 18), _clean(s.get("team","")),              font=font_xs,  fill=C["text_muted"],   anchor="lm")
        draw.text((w - 90, ry + row_h // 2),   str(s.get("goals", 0)),                font=font_xl,  fill=C["text_primary"], anchor="mm")
        draw.text((w - 90, ry + row_h // 2 + 30), "goals",                            font=font_xs,  fill=C["text_muted"],   anchor="mm")

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
    img = _gradient_bg(w, h, (8, 18, 14), (10, 10, 26))

    # Soft green glow behind the header
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(ov).ellipse(
        [(-w * 0.3, -h * 0.25), (w * 1.3, h * 0.45)], fill=(*C["accent_green"], 35)
    )
    img = Image.alpha_composite(img, ov)
    draw = ImageDraw.Draw(img)

    font_header  = _load_font(50, True)
    font_name    = _load_font(64, True)
    font_sub     = _load_font(30)
    font_club    = _load_font(34, True)
    font_label   = _load_font(24, True)
    font_fee_lbl = _load_font(26, True)
    font_fee     = _load_font(56, True)

    # ── Bold green header banner ──
    header_h = 130
    hdr = Image.new("RGBA", (w, header_h), (*C["accent_green"], 255))
    img.paste(hdr, (0, 0), hdr)
    draw = ImageDraw.Draw(img)
    draw.text((w // 2, header_h // 2), "TRANSFER ALERT", font=font_header,
              fill=(255, 255, 255), anchor="mm")

    y = header_h + 70

    # ── Player photo (or initials badge if no photo available) ──
    photo_size = 300
    ring_size  = photo_size + 20
    player_img = _fetch_image(player_photo_url, (photo_size, photo_size)) if player_photo_url else None

    ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring)
    ring_draw.ellipse([(0, 0), (ring_size, ring_size)], fill=C["accent_gold"])

    if player_img:
        mask = Image.new("L", (photo_size, photo_size), 0)
        ImageDraw.Draw(mask).ellipse([(0, 0), (photo_size, photo_size)], fill=255)
        circle = Image.new("RGBA", (photo_size, photo_size), (0, 0, 0, 0))
        circle.paste(player_img, mask=mask)
        ring.paste(circle, (10, 10), circle)
    else:
        ring_draw.ellipse([(10, 10), (ring_size - 10, ring_size - 10)], fill=C["bg_card"])
        initials = "".join(p[0] for p in _clean(player_name).split()[:2]).upper() or "FP"
        ring_draw.text((ring_size // 2, ring_size // 2), initials,
                       font=_load_font(110, True), fill=C["accent_gold"], anchor="mm")

    img.paste(ring, (w // 2 - ring_size // 2, y), ring)
    y += ring_size + 30
    draw = ImageDraw.Draw(img)

    # ── Player name (auto-shrinks to fit width) ──
    name_text = _clean(player_name).upper()
    fit_font = font_name
    while (hasattr(fit_font, "size") and fit_font.size > 32
           and draw.textlength(name_text, font=fit_font) > w - 120):
        fit_font = _load_font(fit_font.size - 4, True)
    draw.text((w // 2, y), name_text, font=fit_font, fill=C["text_primary"], anchor="mm")
    y += 55
    draw.text((w // 2, y), "TRANSFER UPDATE", font=font_sub, fill=C["text_muted"], anchor="mm")
    y += 70

    from_unknown = from_club.strip().lower() in ("unknown", "", "free agent")
    to_unknown   = to_club.strip().lower() in ("unknown", "")

    card_y = y

    if to_unknown:
        # ── Destination not identified yet: a single status panel ──
        box_w, box_h = 760, 260
        box_x = (w - box_w) // 2
        draw.rounded_rectangle([(box_x, card_y), (box_x + box_w, card_y + box_h)],
                                radius=18, outline=C["accent_gold"], width=3)
        icon_r = 50
        icon_cx, icon_cy = w // 2, card_y + 80
        draw.ellipse([(icon_cx - icon_r, icon_cy - icon_r), (icon_cx + icon_r, icon_cy + icon_r)],
                      fill=C["accent_gold"])
        draw.text((icon_cx, icon_cy), "?", font=_load_font(60, True), fill=C["bg_dark"], anchor="mm")
        draw.text((w // 2, card_y + 165), "TRANSFER IN THE WORKS",
                  font=font_club, fill=C["accent_gold"], anchor="mm")
        draw.text((w // 2, card_y + 215), "Follow for confirmation",
                  font=font_sub, fill=C["text_muted"], anchor="mm")
        y = card_y + box_h + 60

    elif from_unknown:
        # ── New signing: single highlighted "TO" card ──
        card_w, card_h = 460, 240
        card_x = (w - card_w) // 2
        draw.rounded_rectangle([(card_x, card_y), (card_x + card_w, card_y + card_h)],
                                radius=18, fill=(*C["accent_green"], 40))
        draw.rounded_rectangle([(card_x, card_y), (card_x + card_w, card_y + card_h)],
                                radius=18, outline=C["accent_green"], width=3)
        draw.text((card_x + card_w // 2, card_y + 32), "NEW SIGNING",
                  font=font_label, fill=C["accent_green"], anchor="mm")

        to_logo = _fetch_image(to_logo_url, (100, 100))
        if to_logo:
            img.paste(to_logo, (card_x + card_w // 2 - 50, card_y + 60), to_logo)
            draw = ImageDraw.Draw(img)

        name_y = card_y + 190
        for line in textwrap.wrap(_clean(to_club), width=18)[:2]:
            draw.text((card_x + card_w // 2, name_y), line, font=font_club,
                      fill=C["text_primary"], anchor="mm")
            name_y += 40

        y = card_y + card_h + 60

    else:
        # ── Standard FROM -> TO transfer ──
        card_w, card_h = 380, 220
        gap = 40
        start_x = (w - (card_w * 2 + gap)) // 2

        from_x = start_x
        to_x   = start_x + card_w + gap

        # FROM card
        draw.rounded_rectangle([(from_x, card_y), (from_x + card_w, card_y + card_h)],
                                radius=18, fill=(*C["bg_card"], 200))
        draw.text((from_x + card_w // 2, card_y + 32), "FROM",
                  font=font_label, fill=C["text_muted"], anchor="mm")
        from_logo = _fetch_image(from_logo_url, (90, 90))
        name_y = card_y + 165
        if from_logo:
            img.paste(from_logo, (from_x + card_w // 2 - 45, card_y + 55), from_logo)
            draw = ImageDraw.Draw(img)
        else:
            name_y = card_y + 115
        for line in textwrap.wrap(_clean(from_club), width=16)[:2]:
            draw.text((from_x + card_w // 2, name_y), line, font=font_club,
                      fill=C["text_primary"], anchor="mm")
            name_y += 40

        # TO card
        draw.rounded_rectangle([(to_x, card_y), (to_x + card_w, card_y + card_h)],
                                radius=18, fill=(*C["accent_green"], 40))
        draw.rounded_rectangle([(to_x, card_y), (to_x + card_w, card_y + card_h)],
                                radius=18, outline=C["accent_green"], width=3)
        draw.text((to_x + card_w // 2, card_y + 32), "TO",
                  font=font_label, fill=C["accent_green"], anchor="mm")
        to_logo = _fetch_image(to_logo_url, (90, 90))
        name_y = card_y + 165
        if to_logo:
            img.paste(to_logo, (to_x + card_w // 2 - 45, card_y + 55), to_logo)
            draw = ImageDraw.Draw(img)
        else:
            name_y = card_y + 115
        for line in textwrap.wrap(_clean(to_club), width=16)[:2]:
            draw.text((to_x + card_w // 2, name_y), line, font=font_club,
                      fill=C["text_primary"], anchor="mm")
            name_y += 40

        # Arrow badge between the two cards (drawn, not text — always renders cleanly)
        arrow_r = 42
        ax, ay = w // 2, card_y + card_h // 2
        draw.ellipse([(ax - arrow_r, ay - arrow_r), (ax + arrow_r, ay + arrow_r)],
                      fill=C["accent_gold"])
        shaft_w, shaft_h = 36, 10
        draw.rectangle(
            [(ax - shaft_w, ay - shaft_h // 2), (ax + shaft_w // 3, ay + shaft_h // 2)],
            fill=C["bg_dark"]
        )
        head = [
            (ax + shaft_w // 3 - 4, ay - 18),
            (ax + shaft_w // 3 - 4, ay + 18),
            (ax + shaft_w // 3 + 22, ay),
        ]
        draw.polygon(head, fill=C["bg_dark"])

        y = card_y + card_h + 60

    # ── Fee panel ──
    fee_w, fee_h = 460, 130
    fee_x = (w - fee_w) // 2
    draw.rounded_rectangle([(fee_x, y), (fee_x + fee_w, y + fee_h)], radius=16, fill=C["accent_gold"])
    draw.text((w // 2, y + 35), "TRANSFER FEE", font=font_fee_lbl, fill=C["bg_dark"], anchor="mm")
    draw.text((w // 2, y + 85), _clean(fee).upper(), font=font_fee, fill=C["bg_dark"], anchor="mm")
    y += fee_h + 70

    _draw_divider(draw, y, w)
    y += 45
    draw.text((w // 2, y), "FOOTBALL PULSE \u2022 TRANSFER CENTRE", font=_load_font(28, True),
              fill=C["accent_gold"], anchor="mm")

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
    img  = _gradient_bg(w, h, (8, 8, 18), (20, 8, 40))
    img  = _add_accent_stripe(img, C["accent_blue"])

    draw     = ImageDraw.Draw(img)
    font_xl  = _load_font(75, True)
    font_sm  = _load_font(36)

    # Strip emoji from category for poster — emoji in caption is fine
    clean_category = _clean(category) or "FOOTBALL FACT"
    draw.text((w // 2, 100), clean_category, font=font_xl, fill=C["accent_gold"], anchor="mm")
    _draw_divider(draw, 150, w)

    lines  = textwrap.wrap(_clean(fact_text), width=28)
    text_y = 270
    for line in lines:
        draw.text((w // 2, text_y), line, font=font_sm, fill=C["text_primary"], anchor="mm")
        text_y += 52

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)
    return _save(img, f"fact_{category.replace(' ', '_')}_{int(datetime.now().timestamp())}")


# ─────────────────────────────────────────────────────────────────────────────

def create_todays_fixtures(
    fixtures: list[dict],
    date_label: str = "TODAY",
    size_key: str = "portrait",
) -> Path:
    w, h = SIZES[size_key]
    img  = _gradient_bg(w, h, C["bg_dark"], (15, 15, 30))
    draw = ImageDraw.Draw(img)

    font_xl  = _load_font(70, True)
    font_med = _load_font(38, True)
    font_sm  = _load_font(28)
    font_xs  = _load_font(22)

    draw.text((w // 2, 80), f"{_clean(date_label)}'S FIXTURES", font=font_xl, fill=C["accent_gold"], anchor="mm")
    _draw_divider(draw, 125, w)

    row_h   = 100
    start_y = 145

    for i, fix in enumerate(fixtures[:10]):
        ry   = start_y + i * row_h
        bg   = (*C["bg_card"], 120) if i % 2 == 0 else (0, 0, 0, 0)
        ov   = Image.new("RGBA", (w, row_h - 6), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rectangle([(40, 0), (w - 40, row_h - 6)], fill=bg)
        img.alpha_composite(ov, (0, ry + 3))
        draw = ImageDraw.Draw(img)

        home = _clean(fix.get("home_team", ""))[:16]
        away = _clean(fix.get("away_team", ""))[:16]
        kt   = _clean(fix.get("kickoff_time", "TBC"))
        comp = _clean(fix.get("competition", ""))[:20]

        draw.text((90,     ry + row_h // 2 - 10), home, font=font_sm,  fill=C["text_primary"], anchor="lm")
        draw.text((w // 2, ry + row_h // 2 - 10), kt,   font=font_med, fill=C["accent_gold"],  anchor="mm")
        draw.text((w - 90, ry + row_h // 2 - 10), away, font=font_sm,  fill=C["text_primary"], anchor="rm")
        draw.text((w // 2, ry + row_h // 2 + 22), comp, font=font_xs,  fill=C["text_muted"],   anchor="mm")

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)
    return _save(img, f"fixtures_{date_label.replace(' ', '_')}")


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _save(img: Image.Image, name: str) -> Path:
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