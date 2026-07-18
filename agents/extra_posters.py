"""
agents/extra_posters.py — Football Pulse AI
Additional poster types: Starting XI, Record Broken, Half Time.
These are imported and called from poster_design_agent.py.
"""

import random
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw

# Re-use everything from the main poster agent
from agents.poster_design_agent import (
    SIZES, C, _load_font, _fetch_image, _gradient_bg,
    _add_accent_stripe, _draw_divider, _draw_branding, _save
)
from utils.logger import setup_logger

logger = setup_logger("poster_agent")


# ─────────────────────────────────────────────────────────────────────────────
# STARTING XI
# ─────────────────────────────────────────────────────────────────────────────

def create_starting_xi(
    team_name: str,
    competition: str,
    players: list[dict],      # list of {"name": str, "number": int, "position": str}
    formation: str = "4-3-3",
    opponent: str = None,
    team_logo_url: str = None,
    size_key: str = "portrait",
) -> Path:
    """
    players: up to 11 dicts with keys: name, number, position
    formation: e.g. "4-3-3", "4-4-2", "3-5-2"
    """
    w, h = SIZES[size_key]
    img  = _gradient_bg(w, h, (5, 10, 25), (10, 20, 50))
    img  = _add_accent_stripe(img, C["accent_blue"])

    draw      = ImageDraw.Draw(img)
    font_xl   = _load_font(72, True)
    font_big  = _load_font(50, True)
    font_med  = _load_font(36, True)
    font_sm   = _load_font(28)
    font_xs   = _load_font(22)
    font_tiny = _load_font(18)

    # ── Header ──────────────────────────────────────────────────────────────
    draw.text((w // 2, 75), "STARTING XI", font=font_xl, fill=C["accent_gold"], anchor="mm")
    draw.text((w // 2, 140), team_name.upper(), font=font_big, fill=C["text_primary"], anchor="mm")
    if opponent:
        draw.text((w // 2, 182), f"vs {opponent} | {competition}", font=font_xs, fill=C["text_muted"], anchor="mm")
    else:
        draw.text((w // 2, 182), competition.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")

    # Formation badge
    draw.rounded_rectangle([(w//2 - 80, 205), (w//2 + 80, 240)], radius=8, fill=C["accent_red"])
    draw.text((w // 2, 222), formation, font=font_sm, fill=C["text_primary"], anchor="mm")

    _draw_divider(draw, 255, w)

    # ── Football pitch outline ───────────────────────────────────────────────
    pitch_top    = 270
    pitch_bottom = h - 110
    pitch_h      = pitch_bottom - pitch_top
    pitch_l      = 60
    pitch_r      = w - 60

    # Pitch background
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle(
        [(pitch_l, pitch_top), (pitch_r, pitch_bottom)],
        fill=(0, 80, 0, 60)
    )
    img = Image.alpha_composite(img, ov)
    draw = ImageDraw.Draw(img)

    # Pitch lines
    line_color = (255, 255, 255, 60)
    draw.rectangle([(pitch_l, pitch_top), (pitch_r, pitch_bottom)], outline=(255, 255, 255, 80), width=2)
    mid_y = pitch_top + pitch_h // 2
    draw.line([(pitch_l, mid_y), (pitch_r, mid_y)], fill=line_color, width=1)
    # Centre circle
    cr = 60
    draw.ellipse([(w//2 - cr, mid_y - cr), (w//2 + cr, mid_y + cr)], outline=line_color, width=1)
    # Penalty areas
    pa_w, pa_h = 260, 100
    draw.rectangle([(w//2 - pa_w//2, pitch_top), (w//2 + pa_w//2, pitch_top + pa_h)], outline=line_color, width=1)
    draw.rectangle([(w//2 - pa_w//2, pitch_bottom - pa_h), (w//2 + pa_w//2, pitch_bottom)], outline=line_color, width=1)

    # ── Player positions ─────────────────────────────────────────────────────
    # Parse formation into rows (from GK to forwards)
    def _formation_rows(f: str) -> list[int]:
        try:
            rows = [int(x) for x in f.split("-")]
            return [1] + rows   # GK always 1
        except Exception:
            return [1, 4, 3, 3]

    rows     = _formation_rows(formation)
    players  = (players or [])[:11]
    # Pad if fewer than 11
    while len(players) < 11:
        players.append({"name": "Player", "number": len(players) + 1, "position": ""})

    pitch_usable_h = pitch_h - 40
    row_gap        = pitch_usable_h // len(rows)
    player_idx     = 0

    for ri, count in enumerate(rows):
        row_y = pitch_top + 20 + ri * row_gap + row_gap // 2
        col_gap = (pitch_r - pitch_l) // (count + 1)

        for ci in range(count):
            if player_idx >= len(players):
                break
            p    = players[player_idx]
            px   = pitch_l + col_gap * (ci + 1)
            player_idx += 1

            # Player circle
            radius = 28
            draw.ellipse(
                [(px - radius, row_y - radius), (px + radius, row_y + radius)],
                fill=C["accent_gold"], outline=C["text_primary"], width=2
            )
            # Jersey number
            draw.text(
                (px, row_y), str(p.get("number", "")),
                font=_load_font(24, True), fill=C["bg_dark"], anchor="mm"
            )
            # Player name below circle
            name = p.get("name", "")
            # Shorten long names
            if " " in name:
                parts = name.split()
                name = parts[-1]  # Last name only on pitch
            draw.text(
                (px, row_y + radius + 16), name,
                font=font_tiny, fill=C["text_primary"], anchor="mm"
            )

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"xi_{team_name.replace(' ', '_')}")


# ─────────────────────────────────────────────────────────────────────────────
# RECORD BROKEN
# ─────────────────────────────────────────────────────────────────────────────

def create_record_broken(
    player_name: str,
    record_text: str,
    previous_holder: str = None,
    competition: str = "",
    player_photo_url: str = None,
    size_key: str = "portrait",
) -> Path:
    w, h = SIZES[size_key]
    img  = _gradient_bg(w, h, (10, 0, 20), (25, 5, 10))

    # Gold burst overlay
    ov  = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d   = ImageDraw.Draw(ov)
    for angle in range(0, 360, 30):
        import math
        x2 = w // 2 + int(math.cos(math.radians(angle)) * w)
        y2 = h // 2 + int(math.sin(math.radians(angle)) * h // 2)
        d.line([(w // 2, h // 3), (x2, y2)], fill=(*C["accent_gold"], 15), width=3)
    img = Image.alpha_composite(img, ov)

    draw     = ImageDraw.Draw(img)
    font_xl  = _load_font(78, True)
    font_big = _load_font(60, True)
    font_med = _load_font(44, True)
    font_sm  = _load_font(34)
    font_xs  = _load_font(26)

    # Trophy emoji header
    draw.text((w // 2, 85), "🏆 RECORD BROKEN", font=font_xl, fill=C["accent_gold"], anchor="mm")
    if competition:
        draw.text((w // 2, 155), competition.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    _draw_divider(draw, 185, w)

    # Player photo
    photo_y = 205
    player_img = _fetch_image(player_photo_url, (240, 240)) if player_photo_url else None
    if player_img:
        mask = Image.new("L", (240, 240), 0)
        ImageDraw.Draw(mask).ellipse([(0, 0), (240, 240)], fill=255)
        circle = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
        circle.paste(player_img, mask=mask)

        # Gold ring
        ring = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([(0, 0), (260, 260)], fill=C["accent_gold"])
        ring.paste(circle, (10, 10), circle)
        img.paste(ring, (w // 2 - 130, photo_y), ring)
        photo_y += 275

    draw = ImageDraw.Draw(img)
    draw.text((w // 2, photo_y), player_name.upper(), font=font_big, fill=C["text_primary"], anchor="mm")
    photo_y += 65

    # Record description wrapped
    import textwrap
    lines = textwrap.wrap(record_text, width=26)
    for line in lines:
        draw.text((w // 2, photo_y), line, font=font_sm, fill=C["accent_gold"], anchor="mm")
        photo_y += 48

    if previous_holder:
        photo_y += 10
        draw.text((w // 2, photo_y), f"Previously: {previous_holder}", font=font_xs, fill=C["text_muted"], anchor="mm")

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"record_{player_name.replace(' ', '_')}")


# ─────────────────────────────────────────────────────────────────────────────
# HALF TIME
# ─────────────────────────────────────────────────────────────────────────────

def create_half_time(
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    competition: str,
    home_logo_url: str = None,
    away_logo_url: str = None,
    size_key: str = "square",
) -> Path:
    w, h = SIZES[size_key]
    img  = _gradient_bg(w, h, (15, 10, 30), (8, 8, 20))

    # Blue horizontal band across middle
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([(0, h // 2 - 8), (w, h // 2 + 8)], fill=(*C["accent_blue"], 60))
    img = Image.alpha_composite(img, ov)

    draw     = ImageDraw.Draw(img)
    font_xl  = _load_font(90, True)
    font_big = _load_font(72, True)
    font_sm  = _load_font(34)
    font_xs  = _load_font(26)

    draw.text((w // 2, 90), "HALF TIME", font=font_xl, fill=C["accent_blue"], anchor="mm")
    draw.text((w // 2, 165), competition.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    _draw_divider(draw, 195, w)

    # Logos + score
    logo_y = 225
    home_logo = _fetch_image(home_logo_url, (130, 130))
    away_logo = _fetch_image(away_logo_url, (130, 130))
    if home_logo: img.paste(home_logo, (90, logo_y), home_logo)
    if away_logo: img.paste(away_logo, (w - 220, logo_y), away_logo)

    draw = ImageDraw.Draw(img)
    score_txt = f"{home_score}  –  {away_score}"
    draw.text((w // 2, logo_y + 58), score_txt, font=font_big, fill=C["text_primary"], anchor="mm")
    draw.text((155,     logo_y + 152), home_team.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")
    draw.text((w - 155, logo_y + 152), away_team.upper(), font=font_xs, fill=C["text_muted"], anchor="mm")

    _draw_divider(draw, h - 90, w)
    _draw_branding(draw, w, h - 50)

    return _save(img, f"halftime_{home_team}_{away_team}")
