from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.router import router as auth_router
from app.common.config import get_settings
from app.common.csrf import AuthSecurityMiddleware
from app.common.errors import (
    AppError,
    ErrorDetail,
    ErrorResponse,
    app_error_handler,
    validation_error_handler,
)
from app.common.readiness import database_is_ready
from app.db.session import DatabaseSession


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings().validate_startup()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Event Registration API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


app.add_middleware(AuthSecurityMiddleware)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.include_router(auth_router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get(
    "/api/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ErrorResponse}},
)
def ready(session: DatabaseSession) -> ReadinessResponse | JSONResponse:
    if not database_is_ready(session):
        error = ErrorResponse(
            error=ErrorDetail(
                code="SERVICE_UNAVAILABLE",
                message="Database is unavailable.",
                details={},
            )
        )
        return JSONResponse(status_code=503, content=error.model_dump())
    return ReadinessResponse()
