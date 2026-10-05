from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.errors import AppError


def insert_user(session: Session, user: User) -> User:
    session.add(user)
    try:
        session.commit()
        session.refresh(user)
    except SQLAlchemyError as exc:
        session.rollback()
        if (
            isinstance(exc, IntegrityError)
            and isinstance(exc.orig, UniqueViolation)
            and exc.orig.diag.constraint_name == "uq_users_email"
        ):
            raise AppError(
                409, "EMAIL_ALREADY_REGISTERED", "Email is already registered."
            ) from None
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None
    return user


def find_user_by_email(session: Session, email: str) -> User | None:
    try:
        return session.scalar(select(User).where(User.email == email))
    except SQLAlchemyError:
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


def find_user_by_id(session: Session, user_id: UUID) -> User | None:
    try:
        return session.get(User, user_id)
    except SQLAlchemyError:
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None
