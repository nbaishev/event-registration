import secrets
from uuid import uuid4

from sqlalchemy.orm import Session

from app.auth import repository
from app.auth.models import User
from app.auth.passwords import hash_password, verify_password
from app.auth.schemas import LoginRequest, RegisterRequest
from app.auth.tokens import TokenPair, issue_access, issue_tokens, verify_token
from app.common.clock import Clock
from app.common.config import Settings
from app.common.errors import AppError


def register_user(session: Session, clock: Clock, email: str, password: str) -> User:
    request = RegisterRequest(email=email, password=password)
    now = clock.now()
    user = User(
        id=uuid4(),
        email=str(request.email),
        password_hash=hash_password(request.password),
        created_at=now,
        updated_at=now,
    )
    return repository.insert_user(session, user)


# Verify a real Argon2id hash even for an unknown account; no static password/secret.
_dummy_hash = hash_password(secrets.token_urlsafe(32))


def login_user(
    session: Session, clock: Clock, settings: Settings, email: str, password: str
) -> tuple[User, TokenPair]:
    request = LoginRequest(email=email, password=password)
    user = repository.find_user_by_email(session, str(request.email))
    valid = verify_password(
        request.password, user.password_hash if user else _dummy_hash
    )
    if user is None or not valid:
        raise AppError(401, "AUTH_INVALID_CREDENTIALS", "Invalid email or password.")
    return user, issue_tokens(user.id, clock, settings)


def current_user(
    session: Session, clock: Clock, settings: Settings, token: str | None
) -> User:
    if not token:
        raise AppError(401, "AUTH_REQUIRED", "Authentication is required.")
    user_id = verify_token(token, "access", clock, settings)
    user = repository.find_user_by_id(session, user_id)
    if user is None:
        raise AppError(401, "AUTH_REQUIRED", "Authentication is required.")
    return user


def refresh_access(
    session: Session, refresh_token: str, clock: Clock, settings: Settings
) -> tuple[User, str]:
    try:
        user_id = verify_token(refresh_token, "refresh", clock, settings)
    except AppError as exc:
        if exc.code != "AUTH_REQUIRED":
            raise
        raise AppError(
            401, "AUTH_REFRESH_INVALID", "Refresh token is invalid."
        ) from None
    user = repository.find_user_by_id(session, user_id)
    if user is None:
        raise AppError(401, "AUTH_REFRESH_INVALID", "Refresh token is invalid.")
    return user, issue_access(user.id, clock, settings)
