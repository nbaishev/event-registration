from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.events.models import Event, EventStatus


def insert_event(session: Session, event: Event) -> bool:
    try:
        # A collision rolls back only this attempt; the transaction stays usable.
        with session.begin_nested():
            session.add(event)
            session.flush()
        session.commit()
        session.refresh(event)
        return True
    except IntegrityError as exc:
        if (
            isinstance(exc.orig, UniqueViolation)
            and exc.orig.diag.constraint_name == "uq_events_slug"
        ):
            return False
        session.rollback()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None
    except SQLAlchemyError:
        session.rollback()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


def list_by_owner(session: Session, owner_id: UUID) -> list[Event]:
    try:
        return list(
            session.scalars(
                select(Event)
                .where(Event.owner_id == owner_id)
                .order_by(Event.created_at.desc(), Event.id.desc())
            )
        )
    except SQLAlchemyError:
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


def find_event(session: Session, event_id: UUID) -> Event | None:
    try:
        return session.get(Event, event_id)
    except SQLAlchemyError:
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


def find_event_for_update(session: Session, event_id: UUID) -> Event | None:
    try:
        return session.scalar(
            select(Event).where(Event.id == event_id).with_for_update()
        )
    except SQLAlchemyError:
        session.rollback()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


def save_event(
    session: Session,
    event: Event,
    updates: dict[str, object],
    *,
    retry_slug: bool,
) -> bool:
    """Save the locked event; return False only for a retriable slug collision."""
    try:
        if retry_slug:
            with session.begin_nested():
                for field, value in updates.items():
                    setattr(event, field, value)
                session.flush()
        else:
            for field, value in updates.items():
                setattr(event, field, value)
            session.flush()
        session.commit()
        session.refresh(event)
        return True
    except IntegrityError as exc:
        is_slug_collision = (
            isinstance(exc.orig, UniqueViolation)
            and exc.orig.diag.constraint_name == "uq_events_slug"
        )
        if retry_slug and is_slug_collision:
            return False
        session.rollback()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None
    except SQLAlchemyError:
        session.rollback()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


def find_public_event(session: Session, slug: str) -> Event | None:
    try:
        return session.scalar(
            select(Event).where(
                Event.slug == slug,
                Event.status.in_([EventStatus.PUBLISHED, EventStatus.CANCELLED]),
            )
        )
    except SQLAlchemyError:
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


def delete_event(session: Session, event: Event) -> None:
    """Delete under the caller's Event lock and transaction."""
    session.delete(event)
