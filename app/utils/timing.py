"""Lightweight timing context manager for logging request latency."""
from __future__ import annotations

import time
from contextlib import contextmanager

from app.core.logging import get_logger

logger = get_logger(__name__)


@contextmanager
def timed(label: str):
    t0 = time.time()
    try:
        yield
    finally:
        logger.info("%s in %.2fs", label, time.time() - t0)
