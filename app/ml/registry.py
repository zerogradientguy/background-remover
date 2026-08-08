"""
Model registry — a single object that owns all heavy ML engines for the app.

Lives at `app.state.registry`. Endpoints pull engines off it via the
`get_registry` dependency so we never reload weights mid-request.
"""
from __future__ import annotations

from app.config import Settings
from app.core.logging import get_logger
from app.ml.birefnet_loader import BiRefNetEngine

logger = get_logger(__name__)


class ModelRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.birefnet = BiRefNetEngine(
            model_id=settings.birefnet_model_id,
            input_size=settings.birefnet_input_size,
        )

    @property
    def device(self) -> str:
        return self.birefnet.device

    def warmup(self) -> None:
        """
        Load the always-on models. The enhancer stack is lazy-loaded on first
        request so cold start stays fast.
        """
        self.birefnet.load()

    def unload(self) -> None:
        self.birefnet.unload()
