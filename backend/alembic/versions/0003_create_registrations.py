"""Create registrations.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "CONFIRMED",
                "WAITLIST",
                "CANCELLED",
                name="registration_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("waitlisted_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("ticket_code", sa.String()),
        sa.Column("ticket_issued_at", sa.DateTime(timezone=True)),
        sa.Column("checked_in_at", sa.DateTime(timezone=True)),
        sa.Column("confirmation_email_sent_at", sa.DateTime(timezone=True)),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("event_id", "user_id", name="uq_registrations_event_user"),
        sa.UniqueConstraint("ticket_code", name="uq_registrations_ticket_code"),
        sa.CheckConstraint(
            "status != 'CONFIRMED' OR (confirmed_at IS NOT NULL AND "
            "waitlisted_at IS NULL AND "
            "cancelled_at IS NULL AND "
            "ticket_code IS NOT NULL AND "
            "ticket_issued_at IS NOT NULL)",
            name="ck_registrations_confirmed",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
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
    )
    op.create_index(
        "ix_registrations_fifo",
        "registrations",
        ["event_id", "waitlisted_at", "id"],
        postgresql_where=sa.text("status = 'WAITLIST'"),
    )


def downgrade() -> None:
    op.drop_index("ix_registrations_fifo", table_name="registrations")
    op.drop_table("registrations")
