"""FastAPI lifespan: load heavy models once at startup, release on shutdown."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.core.logging import get_logger
from app.ml.registry import ModelRegistry

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    registry = ModelRegistry(settings)

    logger.info("Starting %s (env=%s)", settings.app_name, settings.environment)
    t0 = time.time()
    registry.warmup()
    logger.info("Warmup complete in %.1fs (device=%s)", time.time() - t0, registry.device)

    app.state.registry = registry
    app.state.settings = settings

    try:
        yield
    finally:
        logger.info("Shutting down %s", settings.app_name)
        registry.unload()
