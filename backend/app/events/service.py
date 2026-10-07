import re
import secrets
import unicodedata
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.clock import Clock
from app.common.errors import AppError
from app.events import repository
from app.events.models import Event, EventStatus
from app.events.schemas import (
    EventCreateRequest,
    EventPatchRequest,
    PublicEventResponse,
)


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


def patch_owned_event(
    session: Session,
    clock: Clock,
    owner_id: UUID,
    event_id: UUID,
    body: EventPatchRequest,
) -> Event:
    event = repository.find_event_for_update(session, event_id)
    if event is None:
        raise AppError(404, "EVENT_NOT_FOUND", "Event not found.")
    if event.owner_id != owner_id:
        raise AppError(403, "EVENT_NOT_OWNER", "You do not own this event.")
    if event.status == EventStatus.PUBLISHED:
        try:
            if body.model_fields_set != {"capacity"}:
                raise AppError(
                    409, "EVENT_NOT_EDITABLE", "Only published capacity can be edited."
                )
            assert body.capacity is not None
            if body.capacity == event.capacity:
                session.rollback()
                return event
            patch_published_capacity(session, event, clock.now(), body.capacity)
            session.commit()
            return event
        except SQLAlchemyError:
            session.rollback()
            raise AppError(
                503, "SERVICE_UNAVAILABLE", "Database is unavailable."
            ) from None
        except Exception:
            session.rollback()
            raise
    if event.status == EventStatus.CANCELLED:
        raise AppError(409, "EVENT_CANCELLED", "Cancelled events cannot be edited.")

    supplied = body.model_dump(exclude_unset=True)
    regenerate_slug = supplied.pop("regenerate_slug", False)
    changes = {
        field: value
        for field, value in supplied.items()
        if getattr(event, field) != value
    }
    schedule_fields = {"starts_at", "ends_at", "timezone"}
    schedule_changed = bool(schedule_fields.intersection(changes))
    capacity_changed = "capacity" in changes
    merged = {
        "starts_at": changes.get("starts_at", event.starts_at),
        "ends_at": changes.get("ends_at", event.ends_at),
        "capacity": changes.get("capacity", event.capacity),
    }
    if (schedule_changed or capacity_changed) and clock.now() >= event.starts_at:
        raise AppError(409, "EVENT_ALREADY_STARTED", "Event has already started.")
    if merged["ends_at"] <= merged["starts_at"]:
        raise AppError(422, "VALIDATION_ERROR", "End must be after start.")

    now = clock.now()
    if not changes and not regenerate_slug:
        session.rollback()
        return event

    updates = dict(changes)
    if schedule_changed:
        updates["schedule_updated_at"] = now
    updates["updated_at"] = now

    if regenerate_slug:
        for _ in range(5):
            candidate = generate_slug(str(updates.get("title", event.title)))
            if candidate == event.slug:
                continue
            if repository.save_event(
                session, event, updates | {"slug": candidate}, retry_slug=True
            ):
                return event
        session.rollback()
        raise AppError(
            503,
            "SERVICE_UNAVAILABLE",
            "Unable to allocate an event link. Retry the request.",
        )

    repository.save_event(session, event, updates, retry_slug=False)
    return event


def patch_published_capacity(
    session: Session, event: Event, now: datetime, capacity: int
) -> Event:
    """Change capacity under the caller's Event lock and transaction."""
    from app.registrations.promotion import fill_available_slots
    from app.registrations.repository import count_confirmed

    if capacity == event.capacity:
        return event
    if now >= event.starts_at:
        raise AppError(409, "EVENT_ALREADY_STARTED", "Event has already started.")
    if capacity < count_confirmed(session, event.id):
        raise AppError(
            409, "CAPACITY_BELOW_CONFIRMED", "Capacity is below confirmed participants."
        )
    increased = capacity > event.capacity
    event.capacity = capacity
    event.updated_at = now
    # Flush Event before promotion's ticket savepoints; never commit here.
    session.flush()
    if increased:
        fill_available_slots(session, event, now)
    return event


def publish_owned_event(
    session: Session, clock: Clock, owner_id: UUID, event_id: UUID
) -> Event:
    event = repository.find_event_for_update(session, event_id)
    if event is None:
        raise AppError(404, "EVENT_NOT_FOUND", "Event not found.")
    if event.owner_id != owner_id:
        raise AppError(403, "EVENT_NOT_OWNER", "You do not own this event.")
    now = clock.now()
    valid_timezone = True
    try:
        ZoneInfo(event.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        valid_timezone = False
    if (
        event.status != EventStatus.DRAFT
        or event.starts_at <= now
        or event.ends_at <= event.starts_at
        or event.capacity < 1
        or not valid_timezone
    ):
        raise AppError(409, "EVENT_NOT_PUBLISHABLE", "Event cannot be published.")
    repository.save_event(
        session,
        event,
        {
            "status": EventStatus.PUBLISHED,
            "published_at": now,
            "schedule_updated_at": now,
            "updated_at": now,
        },
        retry_slug=False,
    )
    return event


def get_public_event(session: Session, clock: Clock, slug: str) -> PublicEventResponse:
    event = repository.find_public_event(session, slug)
    if event is None:
        raise AppError(404, "EVENT_NOT_FOUND", "Event not found.")
    status = (
        "CANCELLED"
        if event.status == EventStatus.CANCELLED
        else "FINISHED"
        if clock.now() >= event.ends_at
        else "PUBLISHED"
    )
    return PublicEventResponse(
        id=event.id,
        title=event.title,
        description=event.description,
        slug=event.slug,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        timezone=event.timezone,
        capacity=event.capacity,
        status=status,
    )
