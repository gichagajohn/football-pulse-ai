"""
agents/analytics_agent.py — Football Pulse AI
Fetches engagement metrics from Facebook Graph API and stores them
in the engagement table (which has the right columns for this data).
"""

from datetime import datetime, timezone
from typing import Optional

import settings
from database.schema import get_connection
from utils.logger import setup_logger
from utils.http import get_json

logger = setup_logger("analytics_agent")

FB_GRAPH = "https://graph.facebook.com/v19.0"


def _full_post_id(fb_post_id: str) -> str:
    """
    Facebook Graph API requires the full post ID in the format PAGE_ID_POST_ID.
    If the stored ID doesn't already contain an underscore (meaning it's just
    the post portion), prepend the page ID.
    """
    if not fb_post_id or fb_post_id == "skipped":
        return None
    # Already in full format (contains underscore between two numeric parts)
    if "_" in fb_post_id:
        return fb_post_id
    # Prepend page ID
    page_id = settings.FB_PAGE_ID
    if page_id:
        return f"{page_id}_{fb_post_id}"
    return fb_post_id


def fetch_post_insights(fb_post_id: str) -> Optional[dict]:
    """Fetch likes, comments, shares for a FB post. Returns dict or None."""
    if not settings.FB_PAGE_ACCESS_TOKEN:
        return None

    full_id = _full_post_id(fb_post_id)
    if not full_id:
        return None

    fields = "likes.summary(true),comments.summary(true),shares,reactions.summary(true)"
    data = get_json(
        f"{FB_GRAPH}/{full_id}",
        params={
            "fields":       fields,
            "access_token": settings.FB_PAGE_ACCESS_TOKEN,
        }
    )
    if not data:
        return None

    return {
        "likes":    data.get("reactions", {}).get("summary", {}).get("total_count", 0),
        "comments": data.get("comments",  {}).get("summary", {}).get("total_count", 0),
        "shares":   data.get("shares",    {}).get("count", 0),
    }


def update_all_engagement():
    """Pull engagement for all published posts and store in engagement table."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, fb_post_id FROM posts WHERE fb_post_id IS NOT NULL"
        ).fetchall()

    updated = 0
    for row in rows:
        raw_id = row["fb_post_id"]
        if not raw_id or raw_id == "skipped":
            continue

        insights = fetch_post_insights(raw_id)
        if not insights:
            continue

        full_id = _full_post_id(raw_id)

        with get_connection() as conn:
            # Check if we already have an engagement row for this post
            existing = conn.execute(
                "SELECT id FROM engagement WHERE post_id=?",
                (row["id"],)
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE engagement
                       SET likes=?, comments=?, shares=?, fetched_at=CURRENT_TIMESTAMP
                       WHERE post_id=?""",
                    (insights["likes"], insights["comments"],
                     insights["shares"], row["id"])
                )
            else:
                conn.execute(
                    """INSERT INTO engagement
                       (post_id, fb_post_id, platform, likes, comments, shares)
                       VALUES (?, ?, 'facebook', ?, ?, ?)""",
                    (row["id"], full_id,
                     insights["likes"], insights["comments"], insights["shares"])
                )
        updated += 1

    logger.info("Engagement updated for %d posts.", updated)


def get_summary_stats() -> dict:
    """Return aggregated stats for logging."""
    with get_connection() as conn:
        total_posts = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE fb_post_id IS NOT NULL"
        ).fetchone()[0]

        totals = conn.execute(
            """SELECT
               COALESCE(SUM(likes), 0)    as likes,
               COALESCE(SUM(comments), 0) as comments,
               COALESCE(SUM(shares), 0)   as shares
               FROM engagement"""
        ).fetchone()

    return {
        "total_posts":    total_posts,
        "total_likes":    totals["likes"],
        "total_comments": totals["comments"],
        "total_shares":   totals["shares"],
    }


def log_summary():
    stats = get_summary_stats()
    logger.info(
        "📊 Analytics — Posts: %d | Likes: %d | Comments: %d | Shares: %d",
        stats["total_posts"], stats["total_likes"],
        stats["total_comments"], stats["total_shares"]
    )
