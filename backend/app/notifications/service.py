from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.clock import Clock
from app.events.models import Event, EventStatus
from app.notifications.contracts import MailSender
from app.notifications.rendering import render_reminder_email, render_ticket_email
from app.registrations.models import Registration, RegistrationStatus


def confirmation_eligible(
    event: Event, registration: Registration, now: datetime
) -> bool:
    return (
        event.status == EventStatus.PUBLISHED
        and now < event.starts_at
        and registration.status == RegistrationStatus.CONFIRMED
        and registration.confirmation_email_sent_at is None
        and registration.ticket_code is not None
    )


def deliver_confirmation(
    session: Session,
    clock: Clock,
    sender: MailSender,
    event_id: UUID,
    registration_id: UUID,
    app_origin: str,
) -> bool:
    """Own the transaction of a fresh session; hold both locks through SMTP."""
    try:
        event = session.scalar(
            select(Event).where(Event.id == event_id).with_for_update(read=True)
        )
        if event is None:
            session.rollback()
            return False
        registration = session.scalar(
            select(Registration)
            .where(
                Registration.id == registration_id, Registration.event_id == event_id
            )
            .with_for_update()
        )
        now = clock.now()
        if registration is None or not confirmation_eligible(event, registration, now):
            session.rollback()
            return False
        recipient = session.scalar(
            select(User.email).where(User.id == registration.user_id)
        )
        assert recipient is not None
        sender.send(render_ticket_email(recipient, event, registration, app_origin))
        registration.confirmation_email_sent_at = clock.now()
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise


def reminder_eligible(event: Event, registration: Registration, now: datetime) -> bool:
    from app.notifications.eligibility import reminder_conditions

    if registration.confirmed_at is None:
        return False
    return all(
        reminder_conditions(
            event, registration, now, registration.reminder_sent_at is None
        )
    )


def deliver_reminder(
    session: Session,
    clock: Clock,
    sender: MailSender,
    event_id: UUID,
    registration_id: UUID,
    app_origin: str,
) -> bool:
    """Own the transaction of a fresh session; hold both locks through SMTP."""
    try:
        event = session.scalar(
            select(Event).where(Event.id == event_id).with_for_update(read=True)
        )
        if event is None:
            session.rollback()
            return False
        registration = session.scalar(
            select(Registration)
            .where(
                Registration.id == registration_id, Registration.event_id == event_id
            )
            .with_for_update()
        )
        now = clock.now()
        if registration is None or not reminder_eligible(event, registration, now):
            session.rollback()
            return False
        recipient = session.scalar(
            select(User.email).where(User.id == registration.user_id)
        )
        assert recipient is not None
        sender.send(render_reminder_email(recipient, event, registration, app_origin))
        registration.reminder_sent_at = clock.now()
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
