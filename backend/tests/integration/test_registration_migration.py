from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.integration.test_event_draft_edit import create, login

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)
FIELDS = [
    "confirmed_at",
    "waitlisted_at",
    "cancelled_at",
    "ticket_code",
    "ticket_issued_at",
    "checked_in_at",
    "confirmation_email_sent_at",
    "reminder_sent_at",
]
VALID = {
    "CONFIRMED": {
        "confirmed_at": NOW,
        "ticket_code": "23456789ABCD",
        "ticket_issued_at": NOW,
    },
    "WAITLIST": {"waitlisted_at": NOW},
    "CANCELLED": {"cancelled_at": NOW},
}
INVALID = [
    (status, field)
    for status, values in VALID.items()
    for field in FIELDS
    if status != "CONFIRMED"
    or field not in ["checked_in_at", "confirmation_email_sent_at", "reminder_sent_at"]
]


def insert(connection, event_id, user_id, status, values, row_id=None):
    fields = (
        {
            "id": row_id or uuid4(),
            "event_id": event_id,
            "user_id": user_id,
            "status": status,
            "created_at": NOW,
            "updated_at": NOW,
        }
        | dict.fromkeys(FIELDS)
        | values
    )
    columns = ", ".join(fields)
    parameters = ", ".join(":" + field for field in fields)
    connection.execute(
        text(f"INSERT INTO registrations ({columns}) VALUES ({parameters})"), fields
    )


@pytest.mark.parametrize("status,field", INVALID)
def test_each_state_invariant_rejected(auth_client, auth_database, status, field):
    user = login(auth_client)
    event = create(auth_client)
    values = VALID[status].copy()
    values[field] = (
        None if field in values else ("23456789ABCD" if field == "ticket_code" else NOW)
    )
    with pytest.raises(IntegrityError) as error, auth_database.begin() as connection:
        insert(connection, event["id"], user, status, values)
    assert error.value.orig.diag.constraint_name == "ck_registrations_" + status.lower()


def test_unknown_status_unique_fks_and_fifo_index(auth_client, auth_database):
    a = login(auth_client)
    event = create(auth_client)
    auth_client.cookies.clear()
    b = login(auth_client, "b@example.com")
    other_event = create(auth_client)
    with auth_database.begin() as connection:
        insert(connection, event["id"], a, "WAITLIST", VALID["WAITLIST"])
        insert(connection, event["id"], b, "CANCELLED", VALID["CANCELLED"])
    for user, event_id, status, values in [
        (a, event["id"], "WAITLIST", VALID["WAITLIST"]),
        (b, other_event["id"], "UNKNOWN", {}),
        (uuid4(), event["id"], "WAITLIST", VALID["WAITLIST"]),
        (a, uuid4(), "WAITLIST", VALID["WAITLIST"]),
    ]:
        with pytest.raises(IntegrityError), auth_database.begin() as connection:
            insert(connection, event_id, user, status, values)
    with auth_database.begin() as connection:
        connection.execute(text("DELETE FROM registrations"))
        insert(connection, event["id"], a, "CONFIRMED", VALID["CONFIRMED"])
    with pytest.raises(IntegrityError), auth_database.begin() as connection:
        insert(connection, event["id"], b, "CONFIRMED", VALID["CONFIRMED"])
    indexes = inspect(auth_database).get_indexes("registrations")
    fifo = next(index for index in indexes if index["name"] == "ix_registrations_fifo")
    assert fifo["column_names"] == ["event_id", "waitlisted_at", "id"]
    assert "WAITLIST" in str(fifo["dialect_options"]["postgresql_where"])
    assert len(inspect(auth_database).get_foreign_keys("registrations")) == 2
