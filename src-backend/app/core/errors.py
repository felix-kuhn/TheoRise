"""Uniform error responses for the API."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """API error with a machine-readable code and optional details."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str | None = None,
        *,
        details: dict[str, object] | None = None,
        **extra: object,
    ) -> None:
        # `details` is a reserved keyword used by callers that pass a prepared
        # object; remaining keyword arguments become the details themselves.
        self.details = details if details is not None else extra
        self.status_code = status_code
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        detail = exc.detail
        details: dict[str, object]
        if isinstance(detail, dict):
            code = str(detail.get("code") or detail.get("reason") or "http_error")
            message = str(detail.get("message") or detail.get("reason") or detail)
            details = {
                key: value
                for key, value in detail.items()
                if key not in ("code", "message", "reason")
            }
        else:
            code = "http_error"
            message = str(detail) if detail else exc.__class__.__name__
            details = {}
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": message, "details": details},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "An unexpected error occurred",
                "details": {},
            },
        )
