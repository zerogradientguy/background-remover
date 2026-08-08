"""Service: AI Background Remover — BiRefNet cutout."""
from __future__ import annotations

from PIL import Image

from app.core.exceptions import ModelNotReadyError
from app.ml.registry import ModelRegistry


def remove_background(registry: ModelRegistry, image: Image.Image) -> Image.Image:
    if not registry.birefnet.ready:
        raise ModelNotReadyError("Background remover is still warming up.")
    return registry.birefnet.cutout(image)
