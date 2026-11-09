from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: dict[str, list[str]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    time: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
