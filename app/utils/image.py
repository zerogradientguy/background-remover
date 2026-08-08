"""Image IO + compositing helpers used across services."""
from __future__ import annotations

import io

from PIL import Image, ImageFilter

from app.core.exceptions import BadInputError


def read_image_bytes(raw: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        return img
    except Exception as e:
        raise BadInputError(f"Could not decode image: {e}") from e


def to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def composite_blur_background(
    image: Image.Image, mask: Image.Image, blur_radius: int = 18
) -> Image.Image:
    """
    Sharp foreground over a Gaussian-blurred background, using the mask
    as the foreground alpha. Used by AI Blur BG.
    """
    rgb = image.convert("RGB") if image.mode != "RGB" else image
    mask_l = mask.convert("L").resize(rgb.size)
    blurred = rgb.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return Image.composite(rgb, blurred, mask_l)
