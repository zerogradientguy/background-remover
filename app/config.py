"""Application settings, loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI Toolkit API"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"

    # Load models on a background thread so the HTTP port binds immediately.
    # Required on platforms that fail a deploy if the port does not open within
    # a fixed window (e.g. Render's ~90s port scan). Set false to block startup
    # until models are ready.
    warmup_in_background: bool = True

    # BiRefNet
    birefnet_model_id: str = "ZhengPeng7/BiRefNet_lite"
    birefnet_input_size: int = 1024

    # Enhancer caps
    enhancer_max_input_side: int = Field(
        default=0,
        description="Cap longest input side on CPU (0 = no cap). Useful for keeping CPU latency sane.",
    )

    # Request limits
    max_upload_mb: int = 25


@lru_cache
def get_settings() -> Settings:
    return Settings()
