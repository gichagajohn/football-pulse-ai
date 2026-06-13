"""
agents/analytics_agent.py — Football Pulse AI
Fetches engagement metrics from Facebook Graph API and stores them.
"""

from datetime import datetime, timezone
from typing import Optional

import settings
from database.schema import get_connection
from utils.logger import setup_logger
from utils.http import get_json

logger = setup_logger("analytics_agent")

FB_GRAPH = "https://graph.facebook.com/v19.0"


def fetch_post_insights(fb_post_id: str) -> Optional[dict]:
    """
    Fetch likes, comments, shares, reach, impressions for a FB post.
    Returns dict or None.
    """
    if not settings.FB_PAGE_ACCESS_TOKEN:
        return None

    fields = "likes.summary(true),comments.summary(true),shares,reactions.summary(true)"
    data = get_json(
        f"{FB_GRAPH}/{fb_post_id}",
        params={
            "fields":       fields,
            "access_token": settings.FB_PAGE_ACCESS_TOKEN,
        }
    )
    if not data:
        return None

    return {
        "likes":      data.get("reactions", {}).get("summary", {}).get("total_count", 0),
        "comments":   data.get("comments",  {}).get("summary", {}).get("total_count", 0),
        "shares":     data.get("shares",    {}).get("count", 0),
        "reach":      0,   # requires Page Insights permission
        "impressions": 0,
    }


def update_all_engagement():
    """Pull engagement for all published posts and update the DB."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, fb_post_id FROM posts WHERE status='published' AND fb_post_id IS NOT NULL"
        ).fetchall()

    updated = 0
    for row in rows:
        insights = fetch_post_insights(row["fb_post_id"])
        if not insights:
            continue

        with get_connection() as conn:
            # Upsert engagement record
            existing = conn.execute(
                "SELECT id FROM engagement WHERE post_id=?", (row["id"],)
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE engagement SET likes=?, comments=?, shares=?, reach=?,
                       impressions=?, fetched_at=? WHERE post_id=?""",
                    (
                        insights["likes"], insights["comments"], insights["shares"],
                        insights["reach"], insights["impressions"],
                        datetime.now(timezone.utc).isoformat(), row["id"]
                    )
                )
            else:
                conn.execute(
                    """INSERT INTO engagement(post_id, fb_post_id, platform, likes, comments, shares, reach, impressions)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        row["id"], row["fb_post_id"], "facebook",
                        insights["likes"], insights["comments"], insights["shares"],
                        insights["reach"], insights["impressions"],
                    )
                )
        updated += 1

    logger.info("Engagement updated for %d posts.", updated)


def get_summary_stats() -> dict:
    """Return aggregated stats for logging / dashboard."""
    with get_connection() as conn:
        total_posts = conn.execute("SELECT COUNT(*) FROM posts WHERE status='published'").fetchone()[0]
        totals = conn.execute(
            "SELECT SUM(likes) as likes, SUM(comments) as comments, SUM(shares) as shares FROM engagement"
        ).fetchone()

    return {
        "total_posts":    total_posts,
        "total_likes":    totals["likes"]    or 0,
        "total_comments": totals["comments"] or 0,
        "total_shares":   totals["shares"]   or 0,
    }


def log_summary():
    stats = get_summary_stats()
    logger.info(
        "📊 Analytics — Posts: %d | Likes: %d | Comments: %d | Shares: %d",
        stats["total_posts"], stats["total_likes"],
        stats["total_comments"], stats["total_shares"]
    )
