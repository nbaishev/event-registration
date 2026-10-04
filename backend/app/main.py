from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.common.readiness import database_is_ready
from app.db.session import DatabaseSession


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, object]


class ErrorResponse(BaseModel):
    error: ErrorDetail


app = FastAPI(
    title="Event Registration API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


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
