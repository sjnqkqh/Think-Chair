import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app error: method=%s path=%s status=%s detail=%s client=%s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
            request.client.host if request.client else "-",
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled exception: method=%s path=%s query=%s client=%s exc_type=%s",
            request.method,
            request.url.path,
            request.url.query,
            request.client.host if request.client else "-",
            type(exc).__name__,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500, content={"detail": "예기치 못한 오류가 발생했습니다."}
        )
