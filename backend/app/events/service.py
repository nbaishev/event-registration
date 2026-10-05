import re
import secrets
import unicodedata
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.common.clock import Clock
from app.common.errors import AppError
from app.events import repository
from app.events.models import Event, EventStatus
from app.events.schemas import EventCreateRequest


def generate_slug(title: str) -> str:
    ascii_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    )
    base = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:80].rstrip("-")
    return f"{base or 'event'}-{secrets.token_hex(6)}"


def create_event(
    session: Session, clock: Clock, owner_id: UUID, body: EventCreateRequest
) -> Event:
    now = clock.now()
    if body.starts_at <= now:
        raise AppError(422, "VALIDATION_ERROR", "Start must be in the future.")
    for _ in range(5):
        event = Event(
            id=uuid4(),
            owner_id=owner_id,
            title=body.title,
            description=body.description,
            slug=generate_slug(body.title),
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            timezone=body.timezone,
            capacity=body.capacity,
            status=EventStatus.DRAFT,
            schedule_updated_at=now,
            published_at=None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
        )
        if repository.insert_event(session, event):
            return event
    session.rollback()
    raise AppError(
        503,
        "SERVICE_UNAVAILABLE",
        "Unable to allocate an event link. Retry the request.",
    )


def list_owned_events(session: Session, owner_id: UUID) -> list[Event]:
    return repository.list_by_owner(session, owner_id)


def get_owned_event(session: Session, owner_id: UUID, event_id: UUID) -> Event:
    event = repository.find_event(session, event_id)
    if event is None:
        raise AppError(404, "EVENT_NOT_FOUND", "Event not found.")
    if event.owner_id != owner_id:
        raise AppError(403, "EVENT_NOT_OWNER", "You do not own this event.")
    return event
