"""Endpoint: ① AI Background Remover."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response

from app.core.dependencies import get_registry
from app.ml.registry import ModelRegistry
from app.services.background_remover import remove_background
from app.utils.image import read_image_bytes, to_png_bytes
from app.utils.timing import timed

router = APIRouter(prefix="/background-remover", tags=["Background Remover"])


@router.post(
    "",
    summary="Remove background and return a transparent PNG cutout.",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def remove(
    file: UploadFile = File(..., description="Source image (PNG/JPG/WEBP)."),
    registry: ModelRegistry = Depends(get_registry),
) -> Response:
    image = read_image_bytes(await file.read())
    with timed(f"background-remover {image.size}"):
        cutout = remove_background(registry, image)
    return Response(content=to_png_bytes(cutout), media_type="image/png")
