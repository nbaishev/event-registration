from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.registrations.models import RegistrationStatus


class RegistrationResponse(BaseModel):
    id: UUID
    event_id: UUID
    user_id: UUID
    status: RegistrationStatus
    confirmed_at: datetime | None
    waitlisted_at: datetime | None
    cancelled_at: datetime | None
    waitlist_position: int | None
    ticket_code: str | None
    checked_in_at: datetime | None
