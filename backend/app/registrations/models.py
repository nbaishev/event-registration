from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistrationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    WAITLIST = "WAITLIST"
    CANCELLED = "CANCELLED"


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_registrations_event_user"),
        UniqueConstraint("ticket_code", name="uq_registrations_ticket_code"),
        CheckConstraint(
            "status != 'CONFIRMED' OR (confirmed_at IS NOT NULL AND "
            "waitlisted_at IS NULL AND "
            "cancelled_at IS NULL AND "
            "ticket_code IS NOT NULL AND "
            "ticket_issued_at IS NOT NULL)",
            name="ck_registrations_confirmed",
        ),
        CheckConstraint(
            "status != 'WAITLIST' OR (confirmed_at IS NULL AND "
            "waitlisted_at IS NOT NULL AND "
            "cancelled_at IS NULL AND "
            "ticket_code IS NULL AND "
            "ticket_issued_at IS NULL AND "
            "checked_in_at IS NULL AND "
            "confirmation_email_sent_at IS NULL AND "
            "reminder_sent_at IS NULL)",
            name="ck_registrations_waitlist",
        ),
        CheckConstraint(
            "status != 'CANCELLED' OR (confirmed_at IS NULL AND "
            "waitlisted_at IS NULL AND "
            "cancelled_at IS NOT NULL AND "
            "ticket_code IS NULL AND "
            "ticket_issued_at IS NULL AND "
            "checked_in_at IS NULL AND "
            "confirmation_email_sent_at IS NULL AND "
            "reminder_sent_at IS NULL)",
            name="ck_registrations_cancelled",
        ),
        Index(
            "ix_registrations_fifo",
            "event_id",
            "waitlisted_at",
            "id",
            postgresql_where=text("status = 'WAITLIST'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(
            RegistrationStatus,
            name="registration_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    waitlisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ticket_code: Mapped[str | None] = mapped_column(String)
    ticket_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
