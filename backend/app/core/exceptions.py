"""Centralised error handling. Every error leaves the API in one envelope:

{"error": {"code": "...", "message": "...", "fields": {"field": ["msg"]} | null}, "request_id": "..."}
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Base class for expected, client-presentable errors raised by services and routes."""

    status_code = 400
    code = "app_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        fields: dict[str, list[str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.headers = headers
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.fields = fields


class UnauthorizedError(AppError):
    status_code, code = 401, "unauthorized"


class ForbiddenError(AppError):
    status_code, code = 403, "forbidden"


class NotFoundError(AppError):
    status_code, code = 404, "not_found"


class ConflictError(AppError):
    status_code, code = 409, "conflict"


class ServiceUnavailableError(AppError):
    status_code, code = 503, "service_unavailable"


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    fields: dict[str, list[str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    rid = _request_id(request)
    out_headers = dict(headers or {})
    if rid:
        out_headers["X-Request-ID"] = rid
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "fields": fields}, "request_id": rid},
        headers=out_headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            request, exc.status_code, exc.code, exc.message, exc.fields, exc.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return error_response(
            request, exc.status_code, code, message, headers=dict(exc.headers or {})
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ())][1:]  # drop body/query/path prefix
            fields.setdefault(".".join(loc) or "_", []).append(str(err.get("msg", "Invalid value")))
        return error_response(request, 422, "validation_error", "Request validation failed", fields)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Details go to the log (with the request id), never to the client.
        logger.exception("Unhandled error", exc_info=exc)
        return error_response(request, 500, "internal_error", "An unexpected error occurred")


class UnprocessableError(AppError):
    """A well-formed request that breaks a business rule (422), with per-field messages for the form."""

    status_code, code = 422, "validation_error"
