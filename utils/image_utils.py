"""
utils/image_utils.py — Football Pulse AI
Downloads and locally caches team logos and player photos.
Avoids re-downloading the same asset on every poster generation.
"""

import hashlib
import io
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

import settings
from utils.logger import setup_logger

logger = setup_logger("image_utils")

CACHE_DIR = settings.ASSETS_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(url: str, size: tuple) -> Path:
    key = hashlib.md5(f"{url}_{size[0]}x{size[1]}".encode()).hexdigest()
    return CACHE_DIR / f"{key}.png"


def fetch_image(
    url: str,
    size: tuple = (200, 200),
    circle_crop: bool = False,
) -> Optional[Image.Image]:
    """
    Download and resize a remote image with local caching.
    Returns RGBA PIL Image or None.
    """
    if not url:
        return None

    cached = _cache_path(url, size)
    if cached.exists():
        try:
            return Image.open(cached).convert("RGBA")
        except Exception:
            cached.unlink(missing_ok=True)

    try:
        resp = requests.get(url, timeout=12, stream=True)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        img = img.resize(size, Image.LANCZOS)

        if circle_crop:
            mask = Image.new("L", size, 0)
            from PIL import ImageDraw
            ImageDraw.Draw(mask).ellipse([(0, 0), size], fill=255)
            result = Image.new("RGBA", size, (0, 0, 0, 0))
            result.paste(img, mask=mask)
            img = result

        img.save(str(cached), "PNG")
        return img

    except Exception as e:
        logger.debug("Image fetch failed (%s): %s", url[:60], e)
        return None


def clear_cache():
    """Remove all cached images."""
    removed = 0
    for f in CACHE_DIR.glob("*.png"):
        f.unlink()
        removed += 1
    logger.info("Cleared %d cached images.", removed)


def get_cache_size_mb() -> float:
    total = sum(f.stat().st_size for f in CACHE_DIR.glob("*.png"))
    return round(total / (1024 * 1024), 2)
