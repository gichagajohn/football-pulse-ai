"""
agents/publisher_agent.py — Football Pulse AI
Publishes photo + caption posts to Facebook Page using the Meta Graph API.
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
# Facebook photo publishing
# ─────────────────────────────────────────────────────────────────────────────

def publish_to_facebook(
    caption: str,
    post_id_db: int = None,
    image_path: Path = None,
) -> Optional[str]:
    """Publish a local image with its caption to the Facebook Page."""
    if not settings.FB_PAGE_ACCESS_TOKEN or not settings.FB_PAGE_ID:
        logger.warning("Facebook credentials not configured. Skipping publish.")
        return None
    if not caption or len(caption.strip()) < 20:
        _mark_failed(post_id_db, "Caption failed validation")
        return None

    import requests
    try:
        if image_path and Path(image_path).is_file():
            with open(image_path, "rb") as photo:
                resp = requests.post(
                    f"{FB_GRAPH}/{settings.FB_PAGE_ID}/photos",
                    files={"source": (Path(image_path).name, photo, "image/jpeg")},
                    data={
                        "caption": caption,
                        "published": "true",
                        "access_token": settings.FB_PAGE_ACCESS_TOKEN,
                    },
                    timeout=90,
                )
        else:
            logger.warning("No valid image path; using text fallback.")
            resp = requests.post(
                f"{FB_GRAPH}/{settings.FB_PAGE_ID}/feed",
                data={"message": caption, "access_token": settings.FB_PAGE_ACCESS_TOKEN},
                timeout=60,
            )

        result = resp.json()
        if resp.ok and (result.get("id") or result.get("post_id")):
            fb_post_id = result.get("post_id") or result.get("id")
            _mark_published(post_id_db, "facebook", fb_post_id=fb_post_id)
            logger.info("Facebook post published: %s", fb_post_id)
            return fb_post_id

        error = result.get("error", result)
        logger.error("Facebook publish failed: %s", error)
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
        fb_post_id = publish_to_facebook(
            caption,
            post_id_db=post_id_db,
            image_path=image_path,
        )

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
