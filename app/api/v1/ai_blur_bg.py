"""Endpoint: ⑥ AI Blur BG."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from app.core.dependencies import get_registry
from app.ml.registry import ModelRegistry
from app.services.ai_blur_bg import blur_background
from app.utils.image import read_image_bytes, to_png_bytes
from app.utils.timing import timed

router = APIRouter(prefix="/ai-blur-bg", tags=["AI Blur BG"])


@router.post(
    "",
    summary="Detect foreground and blur only the background.",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def blur(
    file: UploadFile = File(...),
    blur_radius: int = Form(18, ge=1, le=100, description="Gaussian blur radius."),
    registry: ModelRegistry = Depends(get_registry),
) -> Response:
    image = read_image_bytes(await file.read())
    with timed(f"ai-blur-bg r={blur_radius} {image.size}"):
        result = blur_background(registry, image, blur_radius=blur_radius)
    return Response(content=to_png_bytes(result), media_type="image/png")
