#!/usr/bin/env python3
"""
main.py — Football Pulse AI
Entry point. Starts the scheduler which runs all agents indefinitely.
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

from utils.logger import setup_logger
from agents.scheduler_agent import start

logger = setup_logger("main")

if __name__ == "__main__":
    logger.info("Starting Football Pulse AI…")
    start()
