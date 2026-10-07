from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from threading import Event as Signal
from time import monotonic
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.clock import FixedClock, get_clock
from app.common.errors import AppError
from app.events import repository as events
from app.events import service
from app.events.models import Event
from app.events.schemas import EventPatchRequest
from app.main import app
from app.registrations import promotion
from app.registrations import service as registrations
from app.registrations.models import Registration
from tests.integration.test_event_draft_edit import headers, patch
from tests.integration.test_event_registration import NOW
from tests.integration.test_registration_cancel import participants
from tests.integration.test_waitlist_promotion import snapshot


def owner_login(client):
    assert (
        client.post(
            "/api/auth/login",
            headers=headers(client),
            json={
                "email": "owner@example.com",
                "password": "a long password",
            },
        ).status_code
        == 200
    )


def event_snapshot(db, event_id):
    with db.connect() as conn:
        return dict(
            conn.execute(select(Event.__table__).where(Event.id == UUID(event_id)))
            .mappings()
            .one()
        )


@pytest.mark.parametrize("capacity", [3, 8])
def test_increase_promotes_multiple_fifo(auth_client, auth_database, capacity):
    event, _ = participants(auth_client, auth_database, 4)
    with Session(auth_database) as session:
        waiting = session.scalars(
            select(Registration)
            .where(Registration.status == "WAITLIST")
            .order_by(Registration.id)
        ).all()
        waiting[-1].waitlisted_at = NOW - timedelta(minutes=1)
        expected = [waiting[-1].id, waiting[0].id, waiting[1].id][: capacity - 1]
        session.commit()
    before_event = event_snapshot(auth_database, event["id"])
    before_rows = snapshot(auth_database)
    owner_login(auth_client)
    later = NOW + timedelta(minutes=1)
    app.dependency_overrides[get_clock] = lambda: FixedClock(later)
    response = patch(auth_client, event["id"], {"capacity": capacity})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert auth_client.get(f"/api/events/{event['id']}").json() == response.json()
    after_event = event_snapshot(auth_database, event["id"])
    assert after_event == before_event | {"capacity": capacity, "updated_at": later}
    after_rows = snapshot(auth_database)
    for old, new in zip(before_rows, after_rows, strict=True):
        if old["id"] not in expected:
            assert new == old
        else:
            assert new["status"] == "CONFIRMED"
            assert (
                new["confirmed_at"]
                == new["ticket_issued_at"]
                == new["updated_at"]
                == later
            )
            assert new["waitlisted_at"] is new["cancelled_at"] is None
            assert (
                new["checked_in_at"]
                is new["confirmation_email_sent_at"]
                is new["reminder_sent_at"]
                is None
            )
            assert new["ticket_code"]
    assert len({row["ticket_code"] for row in after_rows if row["ticket_code"]}) == min(
        capacity, 4
    )


@pytest.mark.parametrize("failure", ["runtime", "database", "ticket"])
def test_capacity_rollback_after_promotion_failure(
    auth_client, auth_database, monkeypatch, failure
):
    event, rows = participants(auth_client, auth_database, 3)
    before_event = event_snapshot(auth_database, event["id"])
    before_rows = snapshot(auth_database)
    real = promotion.confirm_registration
    count = 0

    def fail(session, registration, now):
        nonlocal count
        if count == 0:
            real(session, registration, now)
            count += 1
            return
        if failure == "database":
            raise OperationalError("injected", {}, Exception("injected"))
        if failure == "ticket":
            raise AppError(503, "SERVICE_UNAVAILABLE", "Ticket allocation failed.")
        raise RuntimeError("injected promotion failure")

    monkeypatch.setattr(promotion, "confirm_registration", fail)
    expected = RuntimeError if failure == "runtime" else AppError
    with Session(auth_database) as session:
        with pytest.raises(expected):
            service.patch_owned_event(
                session,
                FixedClock(NOW),
                UUID(event["owner_id"]),
                UUID(event["id"]),
                EventPatchRequest(capacity=3),
            )
        # Explicit rollback must restore state while the session is still usable.
        assert count == 1
        assert session.get(Event, UUID(event["id"])).capacity == 1
    assert event_snapshot(auth_database, event["id"]) == before_event
    assert snapshot(auth_database) == before_rows


def test_published_guards_and_noop(auth_client, auth_database):
    event, _ = participants(auth_client, auth_database, 3)
    owner_login(auth_client)
    assert patch(auth_client, event["id"], {"capacity": 2}).status_code == 200
    before = event_snapshot(auth_database, event["id"])
    before_rows = snapshot(auth_database)
    for body, status, code in [
        ({"capacity": 1}, 409, "CAPACITY_BELOW_CONFIRMED"),
        ({"capacity": 2, "title": event["title"]}, 409, "EVENT_NOT_EDITABLE"),
        ({"capacity": 2, "regenerate_slug": False}, 409, "EVENT_NOT_EDITABLE"),
        *[
            ({"capacity": value}, 422, "VALIDATION_ERROR")
            for value in [0, True, None, "3", 2147483648]
        ],
    ]:
        response = patch(auth_client, event["id"], body)
        assert response.status_code == status
        assert response.json()["error"]["code"] == code
        assert event_snapshot(auth_database, event["id"]) == before
        assert snapshot(auth_database) == before_rows
    assert patch(auth_client, event["id"], {"capacity": 2}).status_code == 200
    assert event_snapshot(auth_database, event["id"]) == before
    assert snapshot(auth_database) == before_rows
    with auth_database.begin() as conn:
        conn.execute(
            text("UPDATE events SET starts_at = :now WHERE id = :id"),
            {"now": NOW, "id": event["id"]},
        )
    before = event_snapshot(auth_database, event["id"])
    assert patch(auth_client, event["id"], {"capacity": 2}).status_code == 200
    assert (
        patch(auth_client, event["id"], {"capacity": 3}).json()["error"]["code"]
        == "EVENT_ALREADY_STARTED"
    )
    assert event_snapshot(auth_database, event["id"]) == before
    assert snapshot(auth_database) == before_rows


def test_decrease_to_confirmed_and_owner_guards(auth_client, auth_database):
    event, _ = participants(auth_client, auth_database, 1)
    assert (
        patch(auth_client, event["id"], {"capacity": 2}).json()["error"]["code"]
        == "EVENT_NOT_OWNER"
    )
    assert (
        patch(auth_client, str(uuid4()), {"capacity": 2}).json()["error"]["code"]
        == "EVENT_NOT_FOUND"
    )
    owner_login(auth_client)
    assert patch(auth_client, event["id"], {"capacity": 3}).status_code == 200
    assert patch(auth_client, event["id"], {"capacity": 1}).status_code == 200
    with auth_database.begin() as conn:
        conn.execute(
            text("UPDATE events SET status = 'CANCELLED' WHERE id = :id"),
            {"id": event["id"]},
        )
    assert (
        patch(auth_client, event["id"], {"capacity": 1}).json()["error"]["code"]
        == "EVENT_CANCELLED"
    )


@pytest.mark.parametrize("first", ["patch", "register"])
def test_decrease_vs_register(auth_client, auth_database, first):
    # One CONFIRMED and one WAITLIST. Reactivate the WAITLIST as a newcomer
    # after clearing it, with one free place before the competing decrease.
    event, rows = participants(auth_client, auth_database, 2)
    with auth_database.begin() as conn:
        conn.execute(
            text("DELETE FROM registrations WHERE id = :id"), {"id": rows[1]["id"]}
        )
        conn.execute(
            text("UPDATE events SET capacity = 2 WHERE id = :id"), {"id": event["id"]}
        )
    owner, eid, newcomer = (
        UUID(event["owner_id"]),
        UUID(event["id"]),
        UUID(rows[1]["user_id"]),
    )

    def attempt(session, kind):
        try:
            if kind == "patch":
                return service.patch_owned_event(
                    session, FixedClock(NOW), owner, eid, EventPatchRequest(capacity=1)
                ).capacity
            return registrations.register_for_event(
                session, FixedClock(NOW), newcomer, eid
            ).status
        except AppError as error:
            return error.code

    # Hold the first operation's Event lock until PostgreSQL proves the other
    # operation is blocked. Exercise both serial orders without timing sleeps.
    with Session(auth_database) as locked:
        events.find_event_for_update(locked, eid)
        blocker = locked.scalar(text("SELECT pg_backend_pid()"))
        ready, pids = Signal(), []
        second = "register" if first == "patch" else "patch"

        def competing():
            with Session(auth_database) as session:
                pids.append(session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return attempt(session, second)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(competing)
            try:
                assert ready.wait(5)
                deadline = monotonic() + 5
                with auth_database.connect() as monitor:
                    while monotonic() < deadline:
                        if blocker in monitor.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": pids[0]}
                        ):
                            break
                    else:
                        pytest.fail("Competing operation did not wait for Event lock")
                first_result = attempt(locked, first)
            finally:
                locked.rollback()
            second_result = future.result(timeout=5)
    assert (first_result, second_result) == (
        (1, "WAITLIST")
        if first == "patch"
        else ("CONFIRMED", "CAPACITY_BELOW_CONFIRMED")
    )
    with auth_database.connect() as conn:
        confirmed = conn.scalar(
            text("SELECT count(*) FROM registrations WHERE status = 'CONFIRMED'")
        )
        capacity = conn.scalar(
            text("SELECT capacity FROM events WHERE id = :id"), {"id": event["id"]}
        )
        assert confirmed == capacity == (1 if first == "patch" else 2)


@pytest.mark.parametrize("competitor", ["cancel", "register"])
def test_increase_vs_cancel_or_register(auth_client, auth_database, competitor):
    event, rows = participants(auth_client, auth_database, 3)
    barrier = Barrier(2)
    eid = UUID(event["id"])

    def attempt(capacity):
        with Session(auth_database) as session:
            barrier.wait(timeout=5)
            if capacity:
                return service.patch_owned_event(
                    session,
                    FixedClock(NOW),
                    UUID(event["owner_id"]),
                    eid,
                    EventPatchRequest(capacity=2),
                ).capacity
            if competitor == "cancel":
                return registrations.cancel_registration(
                    session,
                    FixedClock(NOW),
                    UUID(rows[0]["user_id"]),
                    eid,
                ).status
            # Delete one waiting registration and register that participant anew.
            return registrations.register_for_event(
                session,
                FixedClock(NOW),
                UUID(rows[2]["user_id"]),
                eid,
            ).status

    if competitor == "register":
        with auth_database.begin() as conn:
            conn.execute(
                text("DELETE FROM registrations WHERE id = :id"), {"id": rows[2]["id"]}
            )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, capacity) for capacity in (True, False)]
        results = [future.result(timeout=10) for future in futures]
    assert results == [2, "CANCELLED" if competitor == "cancel" else "WAITLIST"]
    after = snapshot(auth_database)
    assert sum(row["status"] == "CONFIRMED" for row in after) == 2
    if competitor == "register":
        waiting = next(
            row for row in after if str(row["user_id"]) == rows[1]["user_id"]
        )
        assert waiting["status"] == "CONFIRMED"
