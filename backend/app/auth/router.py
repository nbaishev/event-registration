import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.auth.cookies import clear_auth_cookies, set_auth_cookies
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import CsrfResponse, LoginRequest, RegisterRequest, UserResponse
from app.auth.service import login_user, register_user
from app.common.clock import Clock
from app.common.clock import get_clock as get_clock
from app.common.config import Settings, get_settings
from app.common.errors import ErrorResponse
from app.db.session import DatabaseSession

router = APIRouter(prefix="/api/auth", tags=["auth"])


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


@router.post(
    "/login",
    response_model=UserResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def login(
    body: LoginRequest,
    response: Response,
    session: DatabaseSession,
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    user, tokens = login_user(session, clock, settings, str(body.email), body.password)
    set_auth_cookies(response, tokens, settings)
    return UserResponse.model_validate(user)


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        401: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post(
    "/logout",
    status_code=204,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def logout(settings: Annotated[Settings, Depends(get_settings)]) -> Response:
    response = Response(status_code=204)
    clear_auth_cookies(response, settings)
    return response
