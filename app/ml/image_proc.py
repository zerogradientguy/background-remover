"""
Foreground refinement (alpha-aware) — vendored from BiRefNet's image_proc.

Used after BiRefNet predicts the mask to recover clean foreground RGB
under the alpha matte (de-fringes hair / soft edges).
"""
from __future__ import annotations

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms


def _fb_blur_fusion_cpu(image, FG, B, alpha, r: int = 90):
    if isinstance(image, Image.Image):
        image = np.array(image) / 255.0
    blurred_alpha = cv2.blur(alpha, (r, r))[:, :, None]
    blurred_FGA = cv2.blur(FG * alpha, (r, r))
    blurred_FG = blurred_FGA / (blurred_alpha + 1e-5)
    blurred_B1A = cv2.blur(B * (1 - alpha), (r, r))
    blurred_B = blurred_B1A / ((1 - blurred_alpha) + 1e-5)
    FG = blurred_FG + alpha * (image - alpha * blurred_FG - (1 - alpha) * blurred_B)
    return np.clip(FG, 0, 1), blurred_B


def _fb_blur_fusion_cpu_2(image, alpha, r: int = 90):
    alpha = alpha[:, :, None]
    FG, blur_B = _fb_blur_fusion_cpu(image, image, image, alpha, r)
    return _fb_blur_fusion_cpu(image, FG, blur_B, alpha, r=6)[0]


def _mean_blur(x: torch.Tensor, kernel_size: int) -> torch.Tensor:
    if kernel_size % 2 == 0:
        pad_l = kernel_size // 2 - 1
        pad_r = kernel_size // 2
        pad_t = kernel_size // 2 - 1
        pad_b = kernel_size // 2
    else:
        pad_l = pad_r = pad_t = pad_b = kernel_size // 2
    padded = torch.nn.functional.pad(x, (pad_l, pad_r, pad_t, pad_b), mode="replicate")
    return torch.nn.functional.avg_pool2d(
        padded, kernel_size=(kernel_size, kernel_size), stride=1, count_include_pad=False
    )


def _fb_blur_fusion_gpu(image, FG, B, alpha, r: int = 90):
    input_dtype = image.dtype
    image = image.to(torch.float32)
    FG = FG.to(torch.float32)
    B = B.to(torch.float32)
    alpha = alpha.to(torch.float32)

    blurred_alpha = _mean_blur(alpha, kernel_size=r)
    blurred_FGA = _mean_blur(FG * alpha, kernel_size=r)
    blurred_FG = blurred_FGA / (blurred_alpha + 1e-5)
    blurred_B1A = _mean_blur(B * (1 - alpha), kernel_size=r)
    blurred_B = blurred_B1A / ((1 - blurred_alpha) + 1e-5)
    out = blurred_FG + alpha * (image - alpha * blurred_FG - (1 - alpha) * blurred_B)
    out = torch.clamp(out, 0, 1)
    return out.to(input_dtype), blurred_B.to(input_dtype)


def _fb_blur_fusion_gpu_2(image, alpha, r: int = 90):
    FG, blur_B = _fb_blur_fusion_gpu(image, image, image, alpha, r)
    return _fb_blur_fusion_gpu(image, FG, blur_B, alpha, r=6)[0]


def refine_foreground(image: Image.Image, mask: Image.Image, r: int = 90, device: str = "cpu") -> Image.Image:
    """Recover clean RGB foreground under the predicted alpha matte."""
    if mask.size != image.size:
        mask = mask.resize(image.size)

    if device == "cuda":
        img_t = transforms.functional.to_tensor(image).float().cuda().unsqueeze(0)
        mask_t = transforms.functional.to_tensor(mask).float().cuda().unsqueeze(0)
        out = _fb_blur_fusion_gpu_2(img_t, mask_t, r=r)
        out = out.squeeze().mul(255.0).to(torch.uint8)
        out = out.permute(1, 2, 0).contiguous().cpu().numpy().astype(np.uint8)
    else:
        img_np = np.array(image, dtype=np.float32) / 255.0
        mask_np = np.array(mask, dtype=np.float32) / 255.0
        out = _fb_blur_fusion_cpu_2(img_np, mask_np, r=r)
        out = (out * 255.0).astype(np.uint8)

    return Image.fromarray(np.ascontiguousarray(out))
