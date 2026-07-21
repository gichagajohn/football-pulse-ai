"""
agents/publisher_agent.py — Football Pulse AI
Publishes text posts to Facebook Page using the Meta Graph API.
Image/poster publishing removed — posts text-only to the feed.
"""

import os
import re
import time
from pathlib import Path
from typing import Optional

import settings
from database.schema import get_connection
from utils.logger import setup_logger
from utils.http import post_json, get_json

logger = setup_logger("publisher_agent")

FB_GRAPH = "https://graph.facebook.com/v19.0"


# ─────────────────────────────────────────────────────────────────────────────
# Facebook — text-only feed post
# ─────────────────────────────────────────────────────────────────────────────

def publish_to_facebook(
    caption: str,
    post_id_db: int = None,
    image_path: Path = None,   # accepted but ignored — kept for call-site compatibility
) -> Optional[str]:
    """
    Post plain text to the Facebook Page feed.
    Returns the FB post ID on success, None on failure.
    """
    if not settings.FB_PAGE_ACCESS_TOKEN or not settings.FB_PAGE_ID:
        logger.warning("Facebook credentials not configured. Skipping FB publish.")
        return None

    import requests

    try:
        resp = requests.post(
            f"{FB_GRAPH}/{settings.FB_PAGE_ID}/feed",
            data={
                "message":      caption,
                "access_token": settings.FB_PAGE_ACCESS_TOKEN,
            },
            timeout=60,
        )
        result = resp.json()
        logger.info("Feed post result: %s", result)

        if resp.status_code == 200 and "id" in result:
            fb_post_id = result["id"]
            logger.info("Facebook text post published: %s", fb_post_id)
            _mark_published(post_id_db, "facebook", fb_post_id=fb_post_id)
            return fb_post_id

        error = result.get("error", {})
        logger.error(
            "Feed post failed — code:%s type:%s message:%s",
            error.get("code"), error.get("type"), error.get("message"),
        )
        _mark_failed(post_id_db, str(error))
        return None

    except Exception as e:
        logger.exception("Facebook publish exception: %s", e)
        _mark_failed(post_id_db, str(e))
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Instagram — skipped (requires an image; text-only not supported)
# ─────────────────────────────────────────────────────────────────────────────

def publish_to_instagram(
    image_path: Path,
    caption: str,
    post_id_db: int = None,
) -> Optional[str]:
    logger.info("Instagram publishing skipped (text-only mode — no image available).")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main publish entry point
# ─────────────────────────────────────────────────────────────────────────────

def publish(
    image_path: Path,       # accepted but ignored — kept so all call sites work unchanged
    caption: str,
    platforms: list[str] = None,
    post_id_db: int = None,
) -> Optional[str]:
    """Publish text-only to Facebook. Returns fb_post_id."""
    if platforms is None:
        platforms = ["facebook"]

    fb_post_id = None
    if "facebook" in platforms:
        fb_post_id = publish_to_facebook(caption, post_id_db=post_id_db)

    # Instagram skipped — needs an image
    if "instagram" in platforms:
        logger.info("Instagram skipped in text-only mode.")

    return fb_post_id


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def create_post_record(
    event_id: int,
    poster_path: str,
    caption_text: str,
    hashtags: str = "",
    platform: str = "facebook",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO posts(event_id, poster_path, caption_text, hashtags, platform, status)
               VALUES(?,?,?,?,?,'pending')""",
            (event_id, str(poster_path), caption_text, hashtags, platform)
        )
        return cur.lastrowid


def _mark_published(post_id: int, platform: str, fb_post_id: str = None, ig_post_id: str = None):
    if not post_id:
        return
    from datetime import datetime, timezone
    with get_connection() as conn:
        conn.execute(
            """UPDATE posts SET status='published', published_at=?,
               fb_post_id=COALESCE(?,fb_post_id),
               ig_post_id=COALESCE(?,ig_post_id) WHERE id=?""",
            (datetime.now(timezone.utc).isoformat(), fb_post_id, ig_post_id, post_id)
        )


def _mark_failed(post_id: int, error: str):
    if not post_id:
        return
    with get_connection() as conn:
        conn.execute(
            "UPDATE posts SET status='failed', error_message=? WHERE id=?",
            (error[:500], post_id)
        )
