from datetime import timedelta
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.clock import Clock
from app.common.errors import AppError
from app.events import repository as events
from app.events.broadcaster import StatsBroadcaster, publish_stats_changed
from app.events.models import EventStatus
from app.registrations import repository
from app.registrations.schemas import CheckInParticipant, CheckInResponse
from app.registrations.tickets import format_ticket_code


def check_in(
    session: Session,
    clock: Clock,
    owner_id: UUID,
    event_id: UUID,
    ticket_code: str,
    *,
    broadcaster: StatsBroadcaster | None = None,
) -> CheckInResponse:
    try:
        event = events.find_event_for_share(session, event_id)
        if event is None:
            raise AppError(404, "EVENT_NOT_FOUND", "Event not found.")
        if event.owner_id != owner_id:
            raise AppError(403, "EVENT_NOT_OWNER", "Event not owned.")
        if event.status == EventStatus.DRAFT:
            raise AppError(409, "CHECKIN_NOT_OPEN", "Check-in is not open.")
        if event.status == EventStatus.CANCELLED:
            raise AppError(409, "EVENT_CANCELLED", "Event is cancelled.")
        now = clock.now()
        if now >= event.ends_at:
            raise AppError(409, "EVENT_FINISHED", "Event has finished.")
        if now < event.starts_at - timedelta(hours=2):
            raise AppError(409, "CHECKIN_NOT_OPEN", "Check-in is not open.")
        registration = repository.mark_checked_in(session, event_id, ticket_code, now)
        if registration is None:
            existing = repository.find_confirmed_ticket(session, event_id, ticket_code)
            if existing is not None and existing.checked_in_at is not None:
                raise AppError(
                    409, "TICKET_ALREADY_CHECKED_IN", "Ticket already checked in."
                )
            raise AppError(404, "TICKET_NOT_FOUND", "Ticket not found.")
        participant = session.get(User, registration.user_id)
        assert participant is not None
        response = CheckInResponse(
            registration_id=registration.id,
            event_id=event_id,
            ticket_code=format_ticket_code(ticket_code),
            checked_in_at=now,
            participant=CheckInParticipant(
                user_id=participant.id, email=participant.email
            ),
        )
        session.commit()
        publish_stats_changed(broadcaster, event_id)
        return response
    except SQLAlchemyError:
        session.rollback()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None
    except Exception:
        session.rollback()
        raise
