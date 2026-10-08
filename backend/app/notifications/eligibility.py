"""Reminder predicates shared by SQL selection and locked delivery checks."""

from datetime import datetime, timedelta
from typing import Any

from app.events.models import EventStatus
from app.registrations.models import RegistrationStatus


def reminder_conditions(
    event: Any, registration: Any, now: datetime, unsent: Any
) -> tuple[Any, ...]:
    # Accept mapped classes (SQL expressions) or instances (Python values).
    cutoff = event.starts_at - timedelta(hours=24)
    return (
        event.status == EventStatus.PUBLISHED,
        registration.status == RegistrationStatus.CONFIRMED,
        unsent,
        registration.confirmed_at <= cutoff,
        event.schedule_updated_at <= cutoff,
        event.starts_at <= now + timedelta(hours=24),
        now < event.starts_at,
    )
