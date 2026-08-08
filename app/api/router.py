"""Aggregates all v1 feature routers under a single APIRouter."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1 import ai_blur_bg, ai_enhancer, background_remover
from app.core.dependencies import get_registry
from app.ml.registry import ModelRegistry
from app.schemas.common import HealthResponse

api_router = APIRouter()
api_router.include_router(background_remover.router)
api_router.include_router(ai_blur_bg.router)
api_router.include_router(ai_enhancer.router)


@api_router.get("/health", response_model=HealthResponse, tags=["Meta"])
def health(registry: ModelRegistry = Depends(get_registry)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        device=registry.device,
        models={"birefnet": registry.birefnet.ready},
    )
