"""Endpoint: ⑤ AI Enhancer (Real-ESRGAN + GFPGAN, 4× upscale + face restore)."""
from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app.core.exceptions import UnsupportedFeatureError
from app.services.ai_enhancer import EnhancerError, get_enhancer
from app.utils.image import read_image_bytes, to_png_bytes
from app.utils.timing import timed

router = APIRouter(prefix="/ai-enhancer", tags=["AI Enhancer"])

_FIXED_SCALE = 4


@router.post(
    "",
    summary="Enhance an image (4× upscale + face restore).",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def enhance(file: UploadFile = File(...)) -> Response:
    image = read_image_bytes(await file.read())
    enhancer = get_enhancer()
    with timed(f"ai-enhancer x{_FIXED_SCALE} {image.size}"):
        try:
            result = enhancer.enhance(image, scale=_FIXED_SCALE)
        except EnhancerError as e:
            raise UnsupportedFeatureError(str(e), code="enhancer_failed") from e
    return Response(content=to_png_bytes(result), media_type="image/png")
