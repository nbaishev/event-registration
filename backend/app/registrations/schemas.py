from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, StrictStr, field_validator

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


class CheckInRequest(BaseModel):
    ticket_code: StrictStr

    @field_validator("ticket_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        from app.registrations.tickets import normalize_ticket_code

        return normalize_ticket_code(value)


class CheckInParticipant(BaseModel):
    user_id: UUID
    email: str


class CheckInResponse(BaseModel):
    status: Literal["checked_in"] = "checked_in"
    registration_id: UUID
    event_id: UUID
    ticket_code: str
    checked_in_at: datetime
    participant: CheckInParticipant
