import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.database.session import ping_database
from app.schemas.common import ErrorResponse, HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@router.get("/health", response_model=HealthResponse, summary="Liveness and service information")
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
        time=datetime.now(UTC).isoformat(timespec="seconds"),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Readiness: checks the database when one is configured",
)
def readiness(settings: SettingsDep) -> ReadinessResponse:
    if settings.sqlalchemy_url is None:
        # Development/test can run without a database; production settings require one.
        return ReadinessResponse(status="degraded", database="not_configured")
    try:
        ping_database(settings)
    except Exception as exc:  # noqa: BLE001 - any driver error means "not ready"
        logger.warning("database readiness check failed: %s", type(exc).__name__)
        raise ServiceUnavailableError(
            "Database is not reachable", code="database_unavailable"
        ) from exc
    return ReadinessResponse(status="ok", database="ok")
