"""FastAPI lifespan: load heavy models once at startup, release on shutdown."""
from __future__ import annotations

import threading
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

    # Registry is published before warmup so requests can be served (and can
    # report 503 model_not_ready) while weights are still loading.
    app.state.registry = registry
    app.state.settings = settings

    logger.info("Starting %s (env=%s)", settings.app_name, settings.environment)

    def _warmup() -> None:
        t0 = time.time()
        try:
            registry.warmup()
            logger.info(
                "Warmup complete in %.1fs (device=%s)", time.time() - t0, registry.device
            )
        except Exception:
            # Never let a warmup failure kill the process — the liveness probe
            # stays up and /api/v1/health keeps reporting birefnet: false.
            logger.exception("Warmup failed after %.1fs", time.time() - t0)

    if settings.warmup_in_background:
        # Uvicorn runs lifespan startup *before* it binds the listening socket,
        # so a blocking warmup delays port binding. Platforms that wait a fixed
        # window for the port to open (Render's port scan, ECS/ALB health
        # checks) will fail the deploy. Loading off-thread lets the port bind
        # immediately; readiness is reported via /api/v1/health instead.
        threading.Thread(target=_warmup, name="model-warmup", daemon=True).start()
        logger.info("Warmup running in background — serving immediately.")
    else:
        _warmup()

    try:
        yield
    finally:
        logger.info("Shutting down %s", settings.app_name)
        registry.unload()
