from datetime import datetime
from typing import Literal
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


class RegistrationEventSummary(BaseModel):
    id: UUID
    title: str
    slug: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    status: Literal["PUBLISHED", "FINISHED", "CANCELLED"]


class MyRegistrationResponse(BaseModel):
    registration: RegistrationResponse
    event: RegistrationEventSummary
