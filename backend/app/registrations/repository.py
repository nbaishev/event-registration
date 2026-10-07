from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.events.models import Event, EventStatus
from app.registrations.models import Registration, RegistrationStatus
from app.registrations.schemas import RegistrationResponse
from app.registrations.tickets import format_ticket_code


def find_registration_for_update(
    session: Session, event_id: UUID, user_id: UUID
) -> Registration | None:
    return session.scalar(
        select(Registration)
        .where(Registration.event_id == event_id, Registration.user_id == user_id)
        .with_for_update()
    )


def count_confirmed(session: Session, event_id: UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Registration)
            .where(
                Registration.event_id == event_id,
                Registration.status == RegistrationStatus.CONFIRMED,
            )
        )
        or 0
    )


def read_snapshot(
    session: Session, event_id: UUID, user_id: UUID
) -> RegistrationResponse | None:
    queue = (
        select(
            Registration.id,
            func.row_number()
            .over(order_by=(Registration.waitlisted_at, Registration.id))
            .label("position"),
        )
        .where(
            Registration.event_id == event_id,
            Registration.status == RegistrationStatus.WAITLIST,
        )
        .subquery()
    )
    fields = [
        getattr(Registration, name)
        for name in RegistrationResponse.model_fields
        if name != "waitlist_position"
    ]
    row = (
        session.execute(
            select(*fields, queue.c.position.label("waitlist_position"))
            .outerjoin(queue, Registration.id == queue.c.id)
            .where(Registration.event_id == event_id, Registration.user_id == user_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    values = dict(row)
    if values["ticket_code"] is not None:
        values["ticket_code"] = format_ticket_code(values["ticket_code"])
    return RegistrationResponse.model_validate(values)


def find_waitlist_for_update(
    session: Session, event_id: UUID, limit: int
) -> list[Registration]:
    return list(
        session.scalars(
            select(Registration)
            .where(
                Registration.event_id == event_id,
                Registration.status == RegistrationStatus.WAITLIST,
            )
            .order_by(Registration.waitlisted_at.asc(), Registration.id.asc())
            .limit(limit)
            .with_for_update()
        )
    )


def read_my_snapshots(session: Session, user_id: UUID) -> list[dict[str, Any]]:
    queue = (
        select(
            Registration.id,
            func.row_number()
            .over(
                partition_by=Registration.event_id,
                order_by=(Registration.waitlisted_at, Registration.id),
            )
            .label("position"),
        )
        .where(Registration.status == RegistrationStatus.WAITLIST)
        .subquery()
    )
    fields = [
        getattr(Registration, name)
        for name in RegistrationResponse.model_fields
        if name != "waitlist_position"
    ]
    event_fields = [
        getattr(Event, name).label("summary_" + name)
        for name in (
            "id",
            "title",
            "slug",
            "starts_at",
            "ends_at",
            "timezone",
            "status",
        )
    ]
    return [
        dict(row)
        for row in session.execute(
            select(*fields, queue.c.position.label("waitlist_position"), *event_fields)
            .join(Event, Event.id == Registration.event_id)
            .outerjoin(queue, Registration.id == queue.c.id)
            .where(Registration.user_id == user_id, Event.status != EventStatus.DRAFT)
            .order_by(Registration.updated_at.desc(), Registration.id.desc())
        ).mappings()
    ]


def count_registrations(session: Session, event_id: UUID) -> int:
    """Count every registration, including cancelled rows, without committing."""
    return (
        session.scalar(
            select(func.count())
            .select_from(Registration)
            .where(Registration.event_id == event_id)
        )
        or 0
    )
