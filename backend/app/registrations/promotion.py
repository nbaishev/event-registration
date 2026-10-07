from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.events.models import Event, EventStatus
from app.registrations import repository
from app.registrations.service import confirm_registration


def fill_available_slots(session: Session, event: Event, now: datetime) -> list[UUID]:
    """Allocate FIFO seats inside the caller's transaction and Event lock."""
    if event.status != EventStatus.PUBLISHED or now >= event.starts_at:
        return []
    available = event.capacity - repository.count_confirmed(session, event.id)
    if available <= 0:
        return []
    waiting = repository.find_waitlist_for_update(session, event.id, available)
    for registration in waiting:
        confirm_registration(session, registration, now)
    return [registration.id for registration in waiting]
