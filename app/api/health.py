"""
Root-level liveness probe at /health.

Dependency-free — returns 200 as soon as the process is accepting requests,
even before heavy models (BiRefNet, GFPGAN, etc.) finish loading. Designed
for AWS ALB target-group health checks and Kubernetes liveness probes.

Full readiness (per-model status + device) lives at /api/v1/health.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["Meta"], summary="Liveness probe.")
def health() -> dict[str, str]:
    return {"status": "ok"}
