from datetime import UTC, datetime

from fastapi import Response

from app.auth.tokens import ACCESS_TTL, REFRESH_TTL, TokenPair
from app.common.config import Settings

AUTH_COOKIES = [
    ("access_token", "/api/", ACCESS_TTL),
    ("refresh_token", "/api/auth/refresh", REFRESH_TTL),
]


def set_auth_cookies(response: Response, tokens: TokenPair, settings: Settings) -> None:
    for (name, path, ttl), token in zip(
        AUTH_COOKIES, (tokens.access, tokens.refresh), strict=True
    ):
        response.set_cookie(
            name,
            token,
            path=path,
            max_age=ttl,
            httponly=True,
            samesite="lax",
            secure=settings.environment == "production",
        )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name, path, _ in AUTH_COOKIES:
        response.set_cookie(
            name,
            "",
            max_age=0,
            expires=datetime(1970, 1, 1, tzinfo=UTC),
            path=path,
            httponly=True,
            samesite="lax",
            secure=settings.environment == "production",
        )
