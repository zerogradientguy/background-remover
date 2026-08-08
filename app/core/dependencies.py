"""FastAPI dependency providers."""
from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.ml.registry import ModelRegistry


def get_registry(request: Request) -> ModelRegistry:
    return request.app.state.registry


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
