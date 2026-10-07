from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.events.models import Event, EventStatus
from app.events.schemas import StatsResponse
from app.registrations.models import Registration, RegistrationStatus


def get_owned_stats(session: Session, owner_id: UUID, event_id: UUID) -> StatsResponse:
    """Read ownership, lifecycle, capacity and counts in one SQL snapshot."""
    confirmed = Registration.status == RegistrationStatus.CONFIRMED
    statement = (
        select(
            Event.id,
            Event.owner_id,
            Event.status,
            Event.capacity,
            func.count(Registration.id).filter(confirmed).label("confirmed"),
            func.count(Registration.id)
            .filter(Registration.status == RegistrationStatus.WAITLIST)
            .label("waitlist"),
            func.count(Registration.id)
            .filter(confirmed, Registration.checked_in_at.is_not(None))
            .label("checked_in"),
        )
        .outerjoin(Registration, Registration.event_id == Event.id)
        .where(Event.id == event_id)
        .group_by(Event.id)
    )
    try:
        snapshot = session.execute(statement).one_or_none()
    except SQLAlchemyError:
        session.rollback()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None
    if snapshot is None:
        raise AppError(404, "EVENT_NOT_FOUND", "Event not found.")
    if snapshot.owner_id != owner_id:
        raise AppError(403, "EVENT_NOT_OWNER", "Event not owned.")
    if snapshot.status == EventStatus.DRAFT:
        raise AppError(409, "EVENT_NOT_PUBLISHED", "Event is not published.")
    return StatsResponse(
        event_id=snapshot.id,
        capacity=snapshot.capacity,
        confirmed=snapshot.confirmed,
        waitlist=snapshot.waitlist,
        checked_in=snapshot.checked_in,
        available_slots=snapshot.capacity - snapshot.confirmed,
    )
