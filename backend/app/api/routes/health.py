from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.config import settings
from app.db.session import verify_database_connection
from app.schemas.health import (
    ComponentStatus,
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
)

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health",
)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Liveness check",
)
async def liveness() -> LivenessResponse:
    return LivenessResponse(
        status="alive",
        service=settings.app_name,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "One or more dependencies are unavailable",
        }
    },
    summary="Readiness check",
)
async def readiness(
    response: Response,
    database_ready: bool = Depends(verify_database_connection),
) -> ReadinessResponse:
    if not database_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="not_ready",
            checks={
                "database": ComponentStatus(
                    status="unavailable",
                    detail="Database connectivity check failed",
                )
            },
        )

    return ReadinessResponse(
        status="ready",
        checks={"database": ComponentStatus(status="ok")},
    )
