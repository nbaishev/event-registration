import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.auth.schemas import CsrfResponse, RegisterRequest, UserResponse
from app.auth.service import register_user
from app.common.clock import Clock, SystemClock
from app.common.config import Settings, get_settings
from app.common.errors import ErrorResponse
from app.db.session import DatabaseSession

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_clock() -> Clock:
    return SystemClock()


@router.get("/csrf", response_model=CsrfResponse)
def csrf(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> CsrfResponse:
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        "csrf_token",
        token,
        path="/",
        secure=settings.environment == "production",
        httponly=False,
        samesite="lax",
    )
    return CsrfResponse(csrf_token=token)


@router.post(
    "/register",
    status_code=201,
    response_model=UserResponse,
    responses={
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def register(
    body: RegisterRequest,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
) -> UserResponse:
    return UserResponse.model_validate(
        register_user(session, clock, str(body.email), body.password)
    )
