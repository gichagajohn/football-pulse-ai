"""
utils/logger.py — Football Pulse AI
Coloured rotating log setup.
"""

import logging
import logging.handlers
from pathlib import Path
from settings import LOG_DIR, LOG_LEVEL

try:
    import colorlog
    _HAS_COLOR = True
except ImportError:
    _HAS_COLOR = False


def setup_logger(name: str = "football_pulse") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # ── Console handler ────────────────────────────────────────────────────
    ch = logging.StreamHandler()
    if _HAS_COLOR:
        fmt = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)-8s]%(reset)s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "green",
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "bold_red",
            }
        )
    else:
        fmt = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s — %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # ── File handler (rotating 5 MB × 5 backups) ──────────────────────────
    log_file = LOG_DIR / "football_pulse.log"
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
    ))
    logger.addHandler(fh)

    return logger


# Module-level convenience
log = setup_logger()
