from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.clock import FixedClock
from app.events import repository as events
from app.registrations import promotion, service
from app.registrations.models import Registration
from tests.integration.test_event_draft_edit import create, login
from tests.integration.test_event_publish import publish
from tests.integration.test_event_registration import NOW, post
from tests.integration.test_registration_cancel import participants


def snapshot(db):
    with db.connect() as conn:
        return list(
            conn.execute(
                select(Registration.__table__).order_by(Registration.id)
            ).mappings()
        )


@pytest.mark.parametrize("capacity", [2, 5])
def test_fifo_timestamp_tie_and_shortage(auth_client, auth_database, capacity):
    event, rows = participants(auth_client, auth_database, 4)
    # Unrelated event/registration must never enter the selected queue.
    auth_client.cookies.clear()
    login(auth_client, "second-owner@example.com")
    other = create(auth_client)
    assert publish(auth_client, other["id"]).status_code == 200
    auth_client.cookies.clear()
    login(auth_client, "unrelated@example.com")
    unrelated = post(auth_client, other).json()
    before = snapshot(auth_database)
    with Session(auth_database) as session:
        target = events.find_event_for_update(session, UUID(event["id"]))
        waiting = list(
            session.scalars(
                select(Registration)
                .where(
                    Registration.event_id == target.id,
                    Registration.status == "WAITLIST",
                )
                .order_by(Registration.id)
            )
        )
        # First timestamp beats id order; the remaining two test the id tie-break.
        waiting[-1].waitlisted_at = NOW - timedelta(minutes=1)
        expected = [waiting[-1].id, waiting[0].id, waiting[1].id][: capacity - 1]
        target.capacity = capacity
        session.flush()
        promoted = promotion.fill_available_slots(session, target, NOW)
        assert promoted == expected
        session.commit()
    after = snapshot(auth_database)
    for old, new in zip(before, after, strict=True):
        if old["id"] not in promoted:
            assert new == old
        else:
            assert new["status"] == "CONFIRMED"
            assert (
                new["confirmed_at"]
                == new["ticket_issued_at"]
                == new["updated_at"]
                == NOW
            )
            assert new["waitlisted_at"] is None
            assert new["confirmation_email_sent_at"] is new["reminder_sent_at"] is None
            assert new["ticket_code"]
    assert any(row["id"] == UUID(unrelated["id"]) for row in after)


@pytest.mark.parametrize("after_first", [False, True])
def test_cancel_rolls_back_failed_promotion(
    auth_client, auth_database, monkeypatch, after_first
):
    event, rows = participants(auth_client, auth_database, 3)
    if after_first:
        with Session(auth_database) as session:
            target = events.find_event_for_update(session, UUID(event["id"]))
            target.capacity = 2
            session.commit()
    before = snapshot(auth_database)
    real = promotion.confirm_registration
    count = 0

    def fail(session, registration, now):
        nonlocal count
        if after_first and count == 0:
            real(session, registration, now)
            count += 1
            return
        raise RuntimeError("injected promotion failure")

    monkeypatch.setattr(promotion, "confirm_registration", fail)
    with Session(auth_database) as session:
        with pytest.raises(RuntimeError, match="injected"):
            service.cancel_registration(
                session, FixedClock(NOW), UUID(rows[0]["user_id"]), UUID(event["id"])
            )
    assert snapshot(auth_database) == before


@pytest.mark.parametrize(
    "status,started", [("DRAFT", False), ("CANCELLED", False), ("PUBLISHED", True)]
)
def test_ineligible_promotion_is_noop(auth_client, auth_database, status, started):
    event, _ = participants(auth_client, auth_database, 2)
    with Session(auth_database) as session:
        target = events.find_event_for_update(session, UUID(event["id"]))
        target.status = status
        target.capacity = 2
        if started:
            target.starts_at = NOW
        session.commit()
    before = snapshot(auth_database)
    with Session(auth_database) as session:
        target = events.find_event_for_update(session, UUID(event["id"]))
        assert promotion.fill_available_slots(session, target, NOW) == []
        session.commit()
    assert snapshot(auth_database) == before
