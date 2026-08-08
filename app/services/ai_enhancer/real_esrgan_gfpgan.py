"""
Base tier: Real-ESRGAN x4plus background upsampler + GFPGAN face restorer.

Loaded lazily on first call so the API can start fast even when the user
never hits /enhance.
"""
from __future__ import annotations

import numpy as np
import torch
from PIL import Image

from app.config import get_settings
from app.core.compat import install_torchvision_functional_tensor_shim
from app.core.logging import get_logger
from app.services.ai_enhancer.base import Enhancer, EnhancerError

logger = get_logger(__name__)


class BaseEnhancer(Enhancer):
    key = "base"
    label = "Base · Real-ESRGAN + GFPGAN"
    description = "Real-ESRGAN upscaling with GFPGAN face restoration."
    available = True

    def __init__(self) -> None:
        self._restorer = None  # GFPGANer wrapping a Real-ESRGAN bg upsampler

    def _load(self):
        if self._restorer is not None:
            return self._restorer

        install_torchvision_functional_tensor_shim()
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
        from gfpgan import GFPGANer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading Real-ESRGAN + GFPGAN on %s ...", device)

        rrdb = RRDBNet(
            num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4
        )
        bg_upsampler = RealESRGANer(
            scale=4,
            model_path=(
                "https://github.com/xinntao/Real-ESRGAN/releases/download/"
                "v0.1.0/RealESRGAN_x4plus.pth"
            ),
            model=rrdb,
            tile=400,
            tile_pad=10,
            pre_pad=0,
            half=False,
            device=device,
        )
        self._restorer = GFPGANer(
            model_path=(
                "https://github.com/TencentARC/GFPGAN/releases/download/"
                "v1.3.0/GFPGANv1.3.pth"
            ),
            upscale=2,
            arch="clean",
            channel_multiplier=2,
            bg_upsampler=bg_upsampler,
            device=device,
        )
        logger.info("Real-ESRGAN + GFPGAN ready.")
        return self._restorer

    def enhance(self, image: Image.Image, scale: int = 4) -> Image.Image:
        restorer = self._load()
        restorer.upscale = scale
        if restorer.bg_upsampler is not None:
            restorer.bg_upsampler.scale = max(scale, 1)

        settings = get_settings()
        rgb_img = image.convert("RGB")

        cap = settings.enhancer_max_input_side
        if cap and max(rgb_img.size) > cap:
            ratio = cap / max(rgb_img.size)
            new_size = (round(rgb_img.width * ratio), round(rgb_img.height * ratio))
            logger.info("Downscaling enhancer input %s -> %s (cap=%d)", rgb_img.size, new_size, cap)
            rgb_img = rgb_img.resize(new_size, Image.LANCZOS)

        rgb = np.array(rgb_img)
        bgr = rgb[:, :, ::-1]

        try:
            _, _, restored_bgr = restorer.enhance(
                bgr, has_aligned=False, only_center_face=False, paste_back=True
            )
        except Exception as e:
            raise EnhancerError(f"Real-ESRGAN/GFPGAN failed: {e}") from e

        restored_rgb = restored_bgr[:, :, ::-1]
        return Image.fromarray(np.ascontiguousarray(restored_rgb))
