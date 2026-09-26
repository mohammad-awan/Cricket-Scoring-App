import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            status.HTTP_404_NOT_FOUND,
        )


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            status.HTTP_409_CONFLICT,
        )


class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled application error",
        exc_info=exc,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        AppError,
        app_error_handler,
    )

    app.add_exception_handler(
        Exception,
        unexpected_error_handler,
    )