"""
AI Enhancer service — Real-ESRGAN + GFPGAN.

`get_enhancer()` returns a process-wide singleton so the heavy model weights
are loaded once on first call and reused for every subsequent request.
"""
from __future__ import annotations

from app.services.ai_enhancer.base import Enhancer, EnhancerError
from app.services.ai_enhancer.real_esrgan_gfpgan import BaseEnhancer

_singleton: BaseEnhancer | None = None


def get_enhancer() -> BaseEnhancer:
    global _singleton
    if _singleton is None:
        _singleton = BaseEnhancer()
    return _singleton


__all__ = ["Enhancer", "EnhancerError", "BaseEnhancer", "get_enhancer"]
