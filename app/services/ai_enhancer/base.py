"""
Enhancer base class. Kept as a thin ABC so real_esrgan_gfpgan.py (the actual
implementation) can subclass it without changes. We ship a single enhancer
(Real-ESRGAN + GFPGAN); this file exists only as a stable import surface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image


class EnhancerError(RuntimeError):
    """Raised when the enhancer backend cannot run."""


class Enhancer(ABC):
    key: str
    label: str
    description: str
    available: bool = True

    @abstractmethod
    def enhance(self, image: Image.Image, scale: int = 4) -> Image.Image:
        """Return an enhanced RGB image."""
