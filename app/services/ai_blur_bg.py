"""
Service: AI Blur BG — reuses BiRefNet's foreground mask, blurs only the BG.

This is intentionally a thin composition step: the heavy work (mask
prediction) is shared with Background Remover, so the marginal cost of
this feature is just a Gaussian blur + alpha composite.
"""
from __future__ import annotations

from PIL import Image

from app.core.exceptions import ModelNotReadyError
from app.ml.registry import ModelRegistry
from app.utils.image import composite_blur_background


def blur_background(
    registry: ModelRegistry, image: Image.Image, blur_radius: int = 18
) -> Image.Image:
    if not registry.birefnet.ready:
        raise ModelNotReadyError("Blur BG is still warming up.")
    mask = registry.birefnet.predict_mask(image)
    return composite_blur_background(image, mask, blur_radius=blur_radius)
