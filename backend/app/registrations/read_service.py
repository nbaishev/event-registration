from uuid import UUID

from sqlalchemy.orm import Session

from app.common.clock import Clock
from app.registrations.repository import read_my_snapshots
from app.registrations.schemas import (
    MyRegistrationResponse,
    RegistrationEventSummary,
    RegistrationResponse,
)
from app.registrations.tickets import format_ticket_code


def list_my_registrations(
    session: Session, clock: Clock, user_id: UUID
) -> list[MyRegistrationResponse]:
    now = clock.now()
    items = []
    for row in read_my_snapshots(session, user_id):
        event = {
            name: row.pop("summary_" + name)
            for name in RegistrationEventSummary.model_fields
        }
        if event["status"] == "PUBLISHED" and now >= event["ends_at"]:
            event["status"] = "FINISHED"
        if row["ticket_code"] is not None:
            row["ticket_code"] = format_ticket_code(row["ticket_code"])
        items.append(
            MyRegistrationResponse(
                registration=RegistrationResponse.model_validate(row),
                event=RegistrationEventSummary.model_validate(event),
            )
        )
    return items
