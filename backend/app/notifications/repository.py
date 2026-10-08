from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.events.models import Event, EventStatus
from app.registrations.models import Registration, RegistrationStatus


def find_confirmation_candidates(
    session: Session, now: datetime
) -> list[tuple[UUID, UUID]]:
    rows = session.execute(
        select(Event.id, Registration.id)
        .join(Registration, Registration.event_id == Event.id)
        .where(
            Event.status == EventStatus.PUBLISHED,
            Event.starts_at > now,
            Registration.status == RegistrationStatus.CONFIRMED,
            Registration.confirmation_email_sent_at.is_(None),
        )
    )
    return [(event_id, registration_id) for event_id, registration_id in rows]


def find_reminder_candidates(
    session: Session, now: datetime
) -> list[tuple[UUID, UUID]]:
    from app.notifications.eligibility import reminder_conditions

    rows = session.execute(
        select(Event.id, Registration.id)
        .join(Registration, Registration.event_id == Event.id)
        .where(
            *reminder_conditions(
                Event, Registration, now, Registration.reminder_sent_at.is_(None)
            )
        )
    )
    return [(event_id, registration_id) for event_id, registration_id in rows]


def find_transition_recipients(session: Session, event_id: UUID) -> list[str]:
    """Read the recipient snapshot while the caller holds Event FOR UPDATE."""
    return list(
        session.scalars(
            select(User.email)
            .join(Registration, Registration.user_id == User.id)
            .where(
                Registration.event_id == event_id,
                Registration.status.in_(
                    [RegistrationStatus.CONFIRMED, RegistrationStatus.WAITLIST]
                ),
            )
        )
    )
