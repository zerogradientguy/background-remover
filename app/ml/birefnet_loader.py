"""BiRefNet model loader + inference helpers."""
from __future__ import annotations

import io
import time
from typing import Tuple

import torch
from PIL import Image
from torchvision import transforms

from app.core.logging import get_logger
from app.ml.image_proc import refine_foreground

logger = get_logger(__name__)

_NORM_MEAN = [0.485, 0.456, 0.406]
_NORM_STD = [0.229, 0.224, 0.225]


class BiRefNetEngine:
    """
    Wraps a loaded BiRefNet model and exposes:
      - predict_mask(image)  -> grayscale alpha PIL.Image at the original size
      - cutout(image)        -> RGBA PIL.Image with refined foreground over transparent BG
    """

    def __init__(self, model_id: str, input_size: int = 1024) -> None:
        self.model_id = model_id
        self.input_size = input_size
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = None
        self._transform = transforms.Compose(
            [
                transforms.Resize((input_size, input_size)),
                transforms.ToTensor(),
                transforms.Normalize(_NORM_MEAN, _NORM_STD),
            ]
        )

    def load(self) -> None:
        if self._model is not None:
            return

        logger.info("Loading BiRefNet '%s' on %s ...", self.model_id, self.device)
        t0 = time.time()
        torch.set_float32_matmul_precision("high")

        from transformers import AutoModelForImageSegmentation

        model = AutoModelForImageSegmentation.from_pretrained(
            self.model_id, trust_remote_code=True
        )
        model.to(self.device)
        model.eval()
        self._model = model
        logger.info("BiRefNet ready in %.1fs", time.time() - t0)

    def unload(self) -> None:
        self._model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    @property
    def ready(self) -> bool:
        return self._model is not None

    @torch.no_grad()
    def predict_mask(self, image: Image.Image) -> Image.Image:
        if self._model is None:
            raise RuntimeError("BiRefNet model is not loaded.")
        rgb = image.convert("RGB") if image.mode != "RGB" else image
        tensor = self._transform(rgb).unsqueeze(0).to(self.device)
        pred = self._model(tensor)[-1].sigmoid().to(torch.float32).cpu()[0].squeeze()
        mask = transforms.ToPILImage()(pred).resize(rgb.size)
        return mask

    def cutout(self, image: Image.Image) -> Image.Image:
        """Return RGBA cutout (foreground over transparent background)."""
        rgb = image.convert("RGB") if image.mode != "RGB" else image
        mask = self.predict_mask(rgb)
        foreground = refine_foreground(rgb, mask, device=self.device)
        foreground.putalpha(mask)
        return foreground

    def cutout_and_mask(self, image: Image.Image) -> Tuple[Image.Image, Image.Image]:
        """Return (rgba_cutout, grayscale_mask) — used by /blur which needs the mask."""
        rgb = image.convert("RGB") if image.mode != "RGB" else image
        mask = self.predict_mask(rgb)
        foreground = refine_foreground(rgb, mask, device=self.device)
        foreground.putalpha(mask)
        return foreground, mask
