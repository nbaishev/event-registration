from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.clock import FixedClock, get_clock
from app.common.errors import AppError
from app.main import app
from app.registrations import tickets
from app.registrations.models import Registration
from app.registrations.service import register_for_event
from tests.integration.test_event_draft_edit import create, headers, login
from tests.integration.test_event_publish import publish

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def setup_event(client, db, capacity=1):
    owner = login(client)
    event = create(client)
    assert publish(client, event["id"]).status_code == 200
    with db.begin() as connection:
        connection.execute(
            text("UPDATE events SET capacity = :capacity WHERE id = :id"),
            {"capacity": capacity, "id": event["id"]},
        )
    return owner, event


def post(client, event):
    return client.post(
        f"/api/events/{event['id']}/registrations", headers=headers(client)
    )


def test_api_confirmed_waitlist_duplicate_and_own_isolation(auth_client, auth_database):
    _, event = setup_event(auth_client, auth_database)
    assert post(auth_client, event).json()["error"]["code"] == "OWNER_CANNOT_REGISTER"
    auth_client.cookies.clear()
    a = login(auth_client, "a@example.com")
    assert (
        auth_client.get(f"/api/events/{event['id']}/my-registration").json()["error"][
            "code"
        ]
        == "REGISTRATION_NOT_FOUND"
    )
    response = post(auth_client, event)
    assert response.status_code == 201
    saved = response.json()
    assert saved["status"] == "CONFIRMED"
    assert saved["user_id"] == a
    assert saved["confirmed_at"] == "2026-10-04T12:00:00Z"
    assert len(saved["ticket_code"]) == 14
    assert saved["waitlist_position"] is None
    assert set(saved) == {
        "id",
        "event_id",
        "user_id",
        "status",
        "confirmed_at",
        "waitlisted_at",
        "cancelled_at",
        "waitlist_position",
        "ticket_code",
        "checked_in_at",
    }
    assert post(auth_client, event).json()["error"]["code"] == "ALREADY_REGISTERED"
    assert auth_client.get(f"/api/events/{event['id']}/my-registration").json() == saved
    auth_client.cookies.clear()
    b = login(auth_client, "b@example.com")
    waiting = post(auth_client, event)
    assert waiting.status_code == 201
    assert waiting.json()["status"] == "WAITLIST"
    assert waiting.json()["user_id"] == b
    assert waiting.json()["ticket_code"] is None
    assert waiting.json()["waitlist_position"] == 1
    assert (
        auth_client.get(f"/api/events/{event['id']}/my-registration").json()
        == waiting.json()
    )


@pytest.mark.parametrize("duplicate", [False, True])
def test_concurrent_registration(auth_client, auth_database, duplicate):
    _, event = setup_event(auth_client, auth_database)
    auth_client.cookies.clear()
    a = UUID(login(auth_client, "a@example.com"))
    auth_client.cookies.clear()
    b = a if duplicate else UUID(login(auth_client, "b@example.com"))
    barrier = Barrier(2)

    def attempt(user):
        with Session(auth_database) as session:
            barrier.wait(timeout=5)
            try:
                return 201, register_for_event(
                    session, FixedClock(NOW), user, UUID(event["id"])
                ).status
            except AppError as error:
                return error.status, error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, user) for user in (a, b)]
        results = [future.result(timeout=10) for future in futures]
    if duplicate:
        assert sorted(code for code, _ in results) == [201, 409]
        assert (409, "ALREADY_REGISTERED") in results
    else:
        assert sorted(results) == [(201, "CONFIRMED"), (201, "WAITLIST")]
    with auth_database.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM registrations WHERE status = 'CONFIRMED'")
            )
            == 1
        )
        assert connection.scalar(text("SELECT count(*) FROM registrations")) == (
            1 if duplicate else 2
        )


@pytest.mark.parametrize(
    "change,code,status",
    [
        ("status = 'DRAFT'", "EVENT_NOT_FOUND", 404),
        ("status = 'CANCELLED'", "EVENT_CANCELLED", 409),
        ("starts_at = '2026-10-04T12:00:00Z'", "EVENT_ALREADY_STARTED", 409),
        (
            "starts_at = '2026-10-04T10:00:00Z', ends_at = '2026-10-04T12:00:00Z'",
            "EVENT_FINISHED",
            409,
        ),
    ],
)
def test_guard_boundaries_no_mutation(auth_client, auth_database, change, code, status):
    _, event = setup_event(auth_client, auth_database)
    auth_client.cookies.clear()
    login(auth_client, "a@example.com")
    with auth_database.begin() as connection:
        connection.execute(
            text(f"UPDATE events SET {change} WHERE id = :id"), {"id": event["id"]}
        )
    response = post(auth_client, event)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM registrations")) == 0


def test_security_and_missing_event(auth_client, auth_database):
    _, event = setup_event(auth_client, auth_database)
    auth_client.cookies.clear()
    assert post(auth_client, event).status_code == 401
    login(auth_client, "a@example.com")
    url = f"/api/events/{event['id']}/registrations"
    assert auth_client.post(url).status_code == 403
    assert (
        auth_client.post(
            url, headers=headers(auth_client) | {"Origin": "http://evil.example"}
        ).status_code
        == 403
    )
    assert (
        auth_client.post(
            f"/api/events/{uuid4()}/registrations", headers=headers(auth_client)
        ).status_code
        == 404
    )
    assert (
        auth_client.post(
            "/api/events/invalid/registrations", headers=headers(auth_client)
        ).status_code
        == 422
    )
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM registrations")) == 0


def test_ticket_collision_and_exhaustion(auth_client, auth_database, monkeypatch):
    _, event = setup_event(auth_client, auth_database, capacity=3)
    auth_client.cookies.clear()
    login(auth_client, "a@example.com")
    monkeypatch.setattr(tickets, "generate_ticket_code", lambda: "7K4P9Q2M8RTA")
    first = post(auth_client, event).json()
    auth_client.cookies.clear()
    login(auth_client, "b@example.com")
    candidates = iter(["7K4P9Q2M8RTA", "23456789ABCD"])
    monkeypatch.setattr(tickets, "generate_ticket_code", lambda: next(candidates))
    second = post(auth_client, event)
    assert second.status_code == 201
    assert second.json()["ticket_code"] == "2345-6789-ABCD"
    auth_client.cookies.clear()
    login(auth_client, "c@example.com")
    attempts = []

    def collide():
        attempts.append(1)
        return "7K4P9Q2M8RTA"

    monkeypatch.setattr(tickets, "generate_ticket_code", collide)
    assert post(auth_client, event).status_code == 503
    assert len(attempts) == 5
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM registrations")) == 2
        assert (
            connection.scalar(
                text("SELECT ticket_code FROM registrations WHERE id = :id"),
                {"id": first["id"]},
            )
            == "7K4P9Q2M8RTA"
        )


@pytest.mark.parametrize("capacity,want", [(1, "WAITLIST"), (2, "CONFIRMED")])
def test_reactivation_resets_state(auth_client, auth_database, capacity, want):
    _, event = setup_event(auth_client, auth_database, capacity=2)
    auth_client.cookies.clear()
    user = login(auth_client, "a@example.com")
    original = post(auth_client, event).json()
    with auth_database.begin() as connection:
        created = connection.scalar(
            text("SELECT created_at FROM registrations WHERE id = :id"),
            {"id": original["id"]},
        )
        connection.execute(
            text(
                "UPDATE registrations SET status = 'CANCELLED', "
                "confirmed_at = NULL, cancelled_at = :now, "
                "ticket_code = NULL, ticket_issued_at = NULL WHERE id = :id"
            ),
            {"id": original["id"], "now": NOW},
        )
        connection.execute(
            text("UPDATE events SET capacity = :capacity WHERE id = :id"),
            {"id": event["id"], "capacity": capacity},
        )
    auth_client.cookies.clear()
    login(auth_client, "b@example.com")
    assert post(auth_client, event).json()["status"] == "CONFIRMED"
    auth_client.cookies.clear()
    login(auth_client, "c@example.com")
    assert post(auth_client, event).json()["status"] == (
        "WAITLIST" if capacity == 1 else "CONFIRMED"
    )
    # For capacity=2 free one place, retaining an active waitlist in the other case.
    if capacity == 2:
        with auth_database.begin() as connection:
            connection.execute(
                text("UPDATE events SET capacity = 3 WHERE id = :id"),
                {"id": event["id"]},
            )
    # Login existing participant rather than creating a second user.
    h = headers(auth_client)
    assert (
        auth_client.post(
            "/api/auth/login",
            headers=h,
            json={"email": "a@example.com", "password": "a long password"},
        ).status_code
        == 200
    )
    later = datetime(2026, 10, 4, 12, 1, tzinfo=UTC)
    app.dependency_overrides[get_clock] = lambda: FixedClock(later)
    result = post(auth_client, event)
    assert result.status_code == 201
    saved = result.json()
    assert saved["id"] == original["id"]
    assert saved["user_id"] == user
    assert saved["status"] == want
    assert saved["cancelled_at"] is None
    if want == "WAITLIST":
        assert saved["waitlist_position"] == 2
        assert saved["ticket_code"] is None
    else:
        assert saved["ticket_code"] != original["ticket_code"]
    with Session(auth_database) as session:
        row = session.get(Registration, UUID(saved["id"]))
        assert row.created_at == created
        assert (
            row.confirmation_email_sent_at
            is row.reminder_sent_at
            is row.checked_in_at
            is None
        )


def test_own_read_fifo_ties_and_finished_event(auth_client, auth_database):
    _, event = setup_event(auth_client, auth_database)
    for email in ["a@example.com", "b@example.com", "c@example.com"]:
        auth_client.cookies.clear()
        login(auth_client, email)
        assert post(auth_client, event).status_code == 201
    with Session(auth_database) as session:
        rows = session.scalars(
            select(Registration)
            .where(Registration.status == "WAITLIST")
            .order_by(Registration.id)
        ).all()
        positions = {str(row.user_id): index for index, row in enumerate(rows, 1)}
    own = auth_client.get(f"/api/events/{event['id']}/my-registration").json()
    assert own["waitlist_position"] == positions[own["user_id"]]
    with auth_database.begin() as connection:
        connection.execute(
            text(
                "UPDATE events SET starts_at = '2026-10-04T10:00:00Z', "
                "ends_at = '2026-10-04T11:00:00Z' WHERE id = :id"
            ),
            {"id": event["id"]},
        )
    assert auth_client.get(f"/api/events/{event['id']}/my-registration").json() == own


def test_registration_rechecks_time_after_event_lock(auth_client, auth_database):
    from threading import Event as Signal
    from time import monotonic

    from app.events.models import Event

    _, event = setup_event(auth_client, auth_database)
    auth_client.cookies.clear()
    participant = UUID(login(auth_client, "a@example.com"))
    ready = Signal()
    worker = []
    with Session(auth_database) as locked:
        row = locked.get(Event, UUID(event["id"]), with_for_update=True)
        blocker = locked.scalar(text("SELECT pg_backend_pid()"))

        def attempt():
            with Session(auth_database) as session:
                worker.append(session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                with pytest.raises(AppError) as error:
                    register_for_event(session, FixedClock(NOW), participant, row.id)
                assert error.value.code == "EVENT_ALREADY_STARTED"

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(attempt)
            try:
                assert ready.wait(5)
                deadline = monotonic() + 5
                with auth_database.connect() as monitor:
                    while monotonic() < deadline:
                        if blocker in monitor.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": worker[0]}
                        ):
                            break
                    else:
                        pytest.fail("Registration did not wait for Event lock")
                row.starts_at = NOW
                locked.commit()
            finally:
                locked.rollback()
            future.result(timeout=5)
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM registrations")) == 0


def test_ticket_retry_retains_event_lock(auth_client, auth_database, monkeypatch):
    _, event = setup_event(auth_client, auth_database, capacity=2)
    auth_client.cookies.clear()
    login(auth_client, "a@example.com")
    monkeypatch.setattr(tickets, "generate_ticket_code", lambda: "7K4P9Q2M8RTA")
    assert post(auth_client, event).status_code == 201
    auth_client.cookies.clear()
    login(auth_client, "b@example.com")
    attempts = []

    def candidate():
        attempts.append(1)
        if len(attempts) == 2:
            # A separate transaction cannot lock Event while the candidate is retried.
            with (
                pytest.raises(OperationalError) as error,
                auth_database.begin() as connection,
            ):
                connection.execute(
                    text("SELECT id FROM events WHERE id = :id FOR UPDATE NOWAIT"),
                    {"id": event["id"]},
                )
            assert getattr(error.value.orig, "sqlstate", None) == "55P03"
            return "23456789ABCD"
        return "7K4P9Q2M8RTA"

    monkeypatch.setattr(tickets, "generate_ticket_code", candidate)
    assert post(auth_client, event).status_code == 201
    assert len(attempts) == 2


def test_cancelled_own_read_and_exhausted_reactivation_rollback(
    auth_client, auth_database, monkeypatch
):
    _, event = setup_event(auth_client, auth_database, capacity=2)
    auth_client.cookies.clear()
    login(auth_client, "a@example.com")
    monkeypatch.setattr(tickets, "generate_ticket_code", lambda: "7K4P9Q2M8RTA")
    assert post(auth_client, event).status_code == 201
    auth_client.cookies.clear()
    login(auth_client, "b@example.com")
    monkeypatch.setattr(tickets, "generate_ticket_code", lambda: "23456789ABCD")
    original = post(auth_client, event).json()
    with auth_database.begin() as connection:
        connection.execute(
            text(
                "UPDATE registrations SET status = 'CANCELLED', "
                "confirmed_at = NULL, cancelled_at = :now, "
                "ticket_code = NULL, ticket_issued_at = NULL WHERE id = :id"
            ),
            {"id": original["id"], "now": NOW},
        )
    url = f"/api/events/{event['id']}/my-registration"
    cancelled = auth_client.get(url).json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["waitlist_position"] is None
    monkeypatch.setattr(tickets, "generate_ticket_code", lambda: "7K4P9Q2M8RTA")
    assert post(auth_client, event).status_code == 503
    assert auth_client.get(url).json() == cancelled
