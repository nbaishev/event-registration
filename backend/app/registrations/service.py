from datetime import datetime
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.clock import Clock
from app.common.errors import AppError
from app.events import repository as events
from app.events.broadcaster import StatsBroadcaster, publish_stats_changed
from app.events.models import EventStatus
from app.registrations import repository, tickets
from app.registrations.models import Registration, RegistrationStatus
from app.registrations.schemas import RegistrationResponse


def reset_state(registration: Registration, now: datetime) -> None:
    for field in (
        "confirmed_at",
        "waitlisted_at",
        "cancelled_at",
        "ticket_code",
        "ticket_issued_at",
        "checked_in_at",
        "confirmation_email_sent_at",
        "reminder_sent_at",
    ):
        setattr(registration, field, None)
    registration.updated_at = now


def confirm_registration(
    session: Session, registration: Registration, now: datetime
) -> None:
    # No pending/dirty state may precede begin_nested's unconditional flush.
    # Mutate and attach the candidate only inside its savepoint.
    for _ in range(5):
        try:
            with session.begin_nested():
                reset_state(registration, now)
                registration.status = RegistrationStatus.CONFIRMED
                registration.confirmed_at = registration.ticket_issued_at = now
                registration.ticket_code = tickets.generate_ticket_code()
                session.add(registration)
                session.flush()
            return
        except IntegrityError as error:
            if not (
                isinstance(error.orig, UniqueViolation)
                and error.orig.diag.constraint_name == "uq_registrations_ticket_code"
            ):
                raise
    raise AppError(503, "SERVICE_UNAVAILABLE", "Unable to allocate a ticket.")


def register_for_event(
    session: Session,
    clock: Clock,
    user_id: UUID,
    event_id: UUID,
    *,
    broadcaster: StatsBroadcaster | None = None,
) -> RegistrationResponse:
    try:
        event = events.find_event_for_update(session, event_id)
        if event is None or event.status == EventStatus.DRAFT:
            raise AppError(404, "EVENT_NOT_FOUND", "Event not found.")
        if event.owner_id == user_id:
            raise AppError(403, "OWNER_CANNOT_REGISTER", "Owner cannot register.")
        now = clock.now()
        if event.status == EventStatus.CANCELLED:
            raise AppError(409, "EVENT_CANCELLED", "Event is cancelled.")
        if now >= event.ends_at:
            raise AppError(409, "EVENT_FINISHED", "Event has finished.")
        if now >= event.starts_at:
            raise AppError(409, "EVENT_ALREADY_STARTED", "Event has already started.")
        registration = repository.find_registration_for_update(
            session, event_id, user_id
        )
        if (
            registration is not None
            and registration.status != RegistrationStatus.CANCELLED
        ):
            raise AppError(409, "ALREADY_REGISTERED", "User is already registered.")
        available = repository.count_confirmed(session, event_id) < event.capacity
        if registration is None:
            registration = Registration(
                id=uuid4(),
                event_id=event_id,
                user_id=user_id,
                created_at=now,
                updated_at=now,
            )
        if available:
            confirm_registration(session, registration, now)
        else:
            reset_state(registration, now)
            registration.status = RegistrationStatus.WAITLIST
            registration.waitlisted_at = now
            session.add(registration)
            session.flush()
        response = repository.read_snapshot(session, event_id, user_id)
        assert response is not None
        session.commit()
        publish_stats_changed(broadcaster, event_id)
        return response
    except AppError:
        session.rollback()
        raise
    except SQLAlchemyError:
        session.rollback()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


def get_my_registration(
    session: Session, user_id: UUID, event_id: UUID
) -> RegistrationResponse:
    try:
        event = events.find_event(session, event_id)
        if event is None or event.status == EventStatus.DRAFT:
            raise AppError(404, "EVENT_NOT_FOUND", "Event not found.")
        response = repository.read_snapshot(session, event_id, user_id)
        if response is None:
            raise AppError(404, "REGISTRATION_NOT_FOUND", "Registration not found.")
        return response
    except SQLAlchemyError:
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


def cancel_registration(
    session: Session,
    clock: Clock,
    user_id: UUID,
    event_id: UUID,
    *,
    broadcaster: StatsBroadcaster | None = None,
) -> RegistrationResponse:
    from app.registrations.promotion import fill_available_slots

    try:
        event = events.find_event_for_update(session, event_id)
        if event is None or event.status == EventStatus.DRAFT:
            raise AppError(404, "EVENT_NOT_FOUND", "Event not found.")
        now = clock.now()
        if event.status == EventStatus.CANCELLED:
            raise AppError(409, "EVENT_CANCELLED", "Event is cancelled.")
        if now >= event.ends_at:
            raise AppError(409, "EVENT_FINISHED", "Event has finished.")
        if now >= event.starts_at:
            raise AppError(409, "EVENT_ALREADY_STARTED", "Event has already started.")
        registration = repository.find_registration_for_update(
            session, event_id, user_id
        )
        if registration is None or registration.status == RegistrationStatus.CANCELLED:
            raise AppError(404, "REGISTRATION_NOT_FOUND", "Registration not found.")
        confirmed = registration.status == RegistrationStatus.CONFIRMED
        if confirmed and registration.checked_in_at is not None:
            raise AppError(
                409, "TICKET_ALREADY_CHECKED_IN", "Ticket already checked in."
            )
        reset_state(registration, now)
        registration.status = RegistrationStatus.CANCELLED
        registration.cancelled_at = now
        session.flush()
        if confirmed:
            fill_available_slots(session, event, now)
        response = repository.read_snapshot(session, event_id, user_id)
        assert response is not None
        session.commit()
        publish_stats_changed(broadcaster, event_id)
        return response
    except SQLAlchemyError:
        session.rollback()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None
    except Exception:
        session.rollback()
        raise
