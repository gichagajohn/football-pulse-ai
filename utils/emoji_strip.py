"""
utils/emoji_strip.py — Football Pulse AI
Strip emoji characters that PIL/Pillow can't render with system fonts.
The text goes in the caption (where Facebook renders emoji fine),
not on the poster image itself.
"""

import re

# Matches all emoji and most special Unicode symbols
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002500-\U00002BEF"  # chinese/box drawing
    "\U00002702-\U000027B0"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001f926-\U0001f937"
    "\U00010000-\U0010ffff"
    "\u2640-\u2642"
    "\u2600-\u2B55"
    "\u200d"
    "\u23cf"
    "\u23e9"
    "\u231a"
    "\ufe0f"   # variation selector
    "\u3030"
    "]+",
    flags=re.UNICODE,
)


def strip_emoji(text: str) -> str:
    """Remove emoji from text, clean up extra whitespace."""
    return _EMOJI_RE.sub("", text).strip()