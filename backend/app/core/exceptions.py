from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def request_id_headers(request: Request) -> dict[str, str]:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return {REQUEST_ID_HEADER: request_id}
    return {}


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "application_error",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.headers = headers or {}


def error_payload(code: str, message: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    # Imported lazily so the core error layer does not import service modules
    # during application module initialization.
    from app.services.shared.authorization import AccessDeniedError

    @app.exception_handler(AccessDeniedError)
    async def access_denied_error_handler(
        request: Request,
        exc: AccessDeniedError,
    ) -> JSONResponse:
        # Object-level authorization failures are deliberately reported as
        # 404 so callers cannot probe for the existence of other customers'
        # records.
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_payload("not_found", "Resource not found."),
            headers=request_id_headers(request),
        )

    @app.exception_handler(AppError)
    async def app_error_handler(
        request: Request,
        exc: AppError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message),
            headers={**exc.headers, **request_id_headers(request)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": jsonable_encoder(exc.errors()),
                }
            },
            headers=request_id_headers(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        headers = dict(exc.headers or {})
        headers.update(request_id_headers(request))
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload("http_error", jsonable_encoder(exc.detail)),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled exception",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "method": request.method,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload(
                "internal_server_error",
                "An unexpected error occurred.",
            ),
            headers=request_id_headers(request),
        )
