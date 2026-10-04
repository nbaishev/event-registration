from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

import jwt

from app.common.clock import Clock
from app.common.config import Settings
from app.common.errors import AppError

ACCESS_TTL = 900
REFRESH_TTL = 2592000
ISSUER = "event-registration"
AUDIENCE = "event-registration-api"


@dataclass(frozen=True)
class TokenPair:
    access: str = field(repr=False)
    refresh: str = field(repr=False)


def issue_tokens(user_id: UUID, clock: Clock, settings: Settings) -> TokenPair:
    issued_at = int(clock.now().timestamp())

    def encode(kind: str, ttl: int) -> str:
        return jwt.encode(
            {
                "sub": str(user_id),
                "iat": issued_at,
                "exp": issued_at + ttl,
                "iss": ISSUER,
                "aud": AUDIENCE,
                "token_type": kind,
            },
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )

    return TokenPair(encode("access", ACCESS_TTL), encode("refresh", REFRESH_TTL))


def verify_token(
    token: str,
    expected_type: Literal["access", "refresh"],
    clock: Clock,
    settings: Settings,
) -> UUID:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            leeway=0,
            options={
                "require": ["sub", "iat", "exp", "iss", "aud", "token_type"],
                # Clock owns temporal checks; crypto/algorithm/iss/aud stay verified.
                "verify_exp": False,
                "verify_iat": False,
                "strict_aud": True,
            },
        )
        now = clock.now().timestamp()
        if (
            type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
            or not isinstance(claims["sub"], str)
            or claims["iss"] != ISSUER
            or claims["aud"] != AUDIENCE
            or claims["token_type"] != expected_type
            or claims["iat"] > now
            or claims["exp"] <= claims["iat"]
            or now >= claims["exp"]
        ):
            raise ValueError("Invalid claims")
        return UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise AppError(401, "AUTH_REQUIRED", "Authentication is required.") from None
