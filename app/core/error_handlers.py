from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.exceptions import AppError, UnauthorizedError
from app.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        logger.warning(
            "app_error.handled",
            method=request.method,
            path=request.url.path,
            status=exc.status_code,
            detail=exc.detail,
            client=request.client.host if request.client else "-",
        )
        if isinstance(exc, UnauthorizedError) and not request.url.path.startswith(
            "/api"
        ):
            return RedirectResponse(url="/login", status_code=303)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "app_error.unhandled",
            exc_info=exc,
            method=request.method,
            path=request.url.path,
            query=request.url.query,
            client=request.client.host if request.client else "-",
            exception_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500, content={"detail": "예기치 못한 오류가 발생했습니다."}
        )
