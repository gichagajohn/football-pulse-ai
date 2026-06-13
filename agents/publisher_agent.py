"""
agents/publisher_agent.py — Football Pulse AI
Publishes posters and captions to Facebook Page and Instagram Business
using the official Meta Graph API. No browser automation.
"""

import os
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
# Facebook
# ─────────────────────────────────────────────────────────────────────────────

def publish_to_facebook(
    image_path: Path,
    caption: str,
    post_id_db: int = None,
) -> Optional[str]:
    """
    Upload photo + caption to Facebook Page.
    Returns the FB post ID on success, None on failure.
    """
    if not settings.FB_PAGE_ACCESS_TOKEN or not settings.FB_PAGE_ID:
        logger.warning("Facebook credentials not configured. Skipping FB publish.")
        return None

    url = f"{FB_GRAPH}/{settings.FB_PAGE_ID}/photos"

    try:
        with open(image_path, "rb") as f:
            image_data = f.read()

        files = {"source": (image_path.name, image_data, "image/jpeg")}
        data  = {
            "caption":      caption,
            "access_token": settings.FB_PAGE_ACCESS_TOKEN,
            "published":    "true",
        }

        # requests needs form-data for file upload
        import requests
        resp = requests.post(url, data=data, files={"source": (image_path.name, image_data, "image/jpeg")}, timeout=60)
        result = resp.json()

        if resp.status_code == 200 and "id" in result:
            fb_post_id = result["id"]
            logger.info("✅ Facebook post published: %s", fb_post_id)
            _mark_published(post_id_db, "facebook", fb_post_id=fb_post_id)
            return fb_post_id
        else:
            error = result.get("error", {})
            logger.error(
                "❌ Facebook publish failed: %s — %s",
                error.get("code"), error.get("message")
            )
            _mark_failed(post_id_db, str(error))
            return None

    except Exception as e:
        logger.exception("Facebook publish exception: %s", e)
        _mark_failed(post_id_db, str(e))
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Instagram
# ─────────────────────────────────────────────────────────────────────────────

def publish_to_instagram(
    image_path: Path,
    caption: str,
    post_id_db: int = None,
) -> Optional[str]:
    """
    Two-step Instagram Graph API publish:
    1. Create media container (upload image URL)
    2. Publish the container

    NOTE: Instagram requires a publicly accessible image URL.
    For local images, we use a temporary hosting approach via the FB photo endpoint.
    """
    if not settings.FB_PAGE_ACCESS_TOKEN or not settings.IG_USER_ID:
        logger.warning("Instagram credentials not configured. Skipping IG publish.")
        return None

    # Step 1: Create media object
    container_url = f"{FB_GRAPH}/{settings.IG_USER_ID}/media"

    try:
        # Upload to FB first to get a hosted URL
        import requests
        with open(image_path, "rb") as f:
            image_data = f.read()

        fb_upload_url = f"{FB_GRAPH}/{settings.FB_PAGE_ID}/photos"
        fb_resp = requests.post(
            fb_upload_url,
            data={
                "access_token": settings.FB_PAGE_ACCESS_TOKEN,
                "published": "false",  # unpublished — just for hosting
            },
            files={"source": (image_path.name, image_data, "image/jpeg")},
            timeout=60,
        )
        fb_result = fb_resp.json()

        if "id" not in fb_result:
            logger.error("Could not upload image to FB for IG hosting: %s", fb_result)
            return None

        # Get URL of the uploaded photo
        photo_id   = fb_result["id"]
        photo_data = get_json(
            f"{FB_GRAPH}/{photo_id}",
            params={"fields": "images", "access_token": settings.FB_PAGE_ACCESS_TOKEN}
        )
        if not photo_data or "images" not in photo_data:
            logger.error("Could not retrieve image URL for IG: %s", photo_data)
            return None

        image_url = photo_data["images"][0]["source"]

        # Create IG media container
        container_resp = requests.post(
            container_url,
            data={
                "image_url":    image_url,
                "caption":      caption,
                "access_token": settings.FB_PAGE_ACCESS_TOKEN,
            },
            timeout=30,
        )
        container_result = container_resp.json()

        if "id" not in container_result:
            logger.error("IG container creation failed: %s", container_result)
            return None

        container_id = container_result["id"]

        # Wait for container to process
        time.sleep(5)
        _wait_for_ig_container(container_id)

        # Step 2: Publish
        publish_url = f"{FB_GRAPH}/{settings.IG_USER_ID}/media_publish"
        pub_resp = requests.post(
            publish_url,
            data={
                "creation_id":  container_id,
                "access_token": settings.FB_PAGE_ACCESS_TOKEN,
            },
            timeout=30,
        )
        pub_result = pub_resp.json()

        if "id" in pub_result:
            ig_post_id = pub_result["id"]
            logger.info("✅ Instagram post published: %s", ig_post_id)
            _mark_published(post_id_db, "instagram", ig_post_id=ig_post_id)
            return ig_post_id
        else:
            logger.error("IG publish failed: %s", pub_result)
            _mark_failed(post_id_db, str(pub_result))
            return None

    except Exception as e:
        logger.exception("Instagram publish exception: %s", e)
        _mark_failed(post_id_db, str(e))
        return None


def _wait_for_ig_container(container_id: str, max_wait: int = 60):
    """Poll until IG media container is ready."""
    for _ in range(max_wait // 5):
        data = get_json(
            f"{FB_GRAPH}/{container_id}",
            params={"fields": "status_code", "access_token": settings.FB_PAGE_ACCESS_TOKEN}
        )
        if data and data.get("status_code") == "FINISHED":
            return True
        time.sleep(5)
    logger.warning("IG container %s did not finish in time.", container_id)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Publish to both platforms
# ─────────────────────────────────────────────────────────────────────────────

def publish(
    image_path: Path,
    caption: str,
    platforms: list[str] = None,
    post_id_db: int = None,
) -> dict:
    """
    Publish to specified platforms.
    platforms: ['facebook'], ['instagram'], or ['facebook', 'instagram']
    Returns dict with fb_post_id, ig_post_id.
    """
    if platforms is None:
        platforms = ["facebook"]

    result = {}
    if "facebook" in platforms:
        result["fb_post_id"] = publish_to_facebook(image_path, caption, post_id_db)

    if "instagram" in platforms:
        result["ig_post_id"] = publish_to_instagram(image_path, caption, post_id_db)

    return result


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
            """UPDATE posts SET status='published', published_at=?, fb_post_id=COALESCE(?,fb_post_id),
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
