from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from threading import Event as Signal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.clock import FixedClock, get_clock
from app.common.errors import AppError
from app.main import app
from app.registrations import checkin, service
from app.registrations.models import Registration
from tests.integration.test_event_draft_edit import headers, login
from tests.integration.test_event_registration import NOW, post, setup_event


def fixture_ticket(client, db):
    owner, event = setup_event(client, db)
    client.cookies.clear()
    login(client, "participant@example.com")
    registration = post(client, event).json()
    with db.begin() as conn:
        conn.execute(
            text("UPDATE events SET starts_at = :start, ends_at = :end WHERE id = :id"),
            {
                "start": NOW + timedelta(hours=2),
                "end": NOW + timedelta(hours=3),
                "id": event["id"],
            },
        )
    sign_in_owner(client)
    return UUID(owner), event, registration


def sign_in_owner(client):
    response = client.post(
        "/api/auth/login",
        headers=headers(client),
        json={"email": "owner@example.com", "password": "a long password"},
    )
    assert response.status_code == 200


def submit(client, event, code):
    return client.post(
        f"/api/events/{event['id']}/check-ins",
        headers=headers(client),
        json={"ticket_code": code},
    )


def test_api_success_duplicate_and_invariants(auth_client, auth_database):
    _, event, row = fixture_ticket(auth_client, auth_database)
    response = submit(auth_client, event, " " + row["ticket_code"].lower() + " ")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "checked_in",
        "registration_id": row["id"],
        "event_id": event["id"],
        "ticket_code": row["ticket_code"],
        "checked_in_at": "2026-10-04T12:00:00Z",
        "participant": {"user_id": row["user_id"], "email": "participant@example.com"},
    }
    repeated = submit(auth_client, event, row["ticket_code"])
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "TICKET_ALREADY_CHECKED_IN"
    assert repeated.headers["cache-control"] == "no-store"
    with Session(auth_database) as session:
        saved = session.get(Registration, UUID(row["id"]))
        assert saved.updated_at == saved.checked_in_at == NOW
        assert saved.confirmed_at == saved.ticket_issued_at == NOW
        assert saved.cancelled_at is None
        assert saved.status == "CONFIRMED"


@pytest.mark.parametrize(
    "offset,code",
    [
        (-1, "CHECKIN_NOT_OPEN"),
        (0, None),
        (3 * 3600 * 1000000 - 1, None),
        (3 * 3600 * 1000000, "EVENT_FINISHED"),
    ],
)
def test_window_boundaries(auth_client, auth_database, offset, code):
    _, event, row = fixture_ticket(auth_client, auth_database)
    instant = NOW + timedelta(microseconds=offset)
    # Refresh login at this instant to avoid expired auth obscuring business time.
    app.dependency_overrides[get_clock] = lambda: FixedClock(instant)
    sign_in_owner(auth_client)
    result = submit(auth_client, event, row["ticket_code"])
    assert result.status_code == (200 if code is None else 409)
    if code:
        assert result.json()["error"]["code"] == code


def test_security_validation_and_event_guards(auth_client, auth_database):
    _, event, row = fixture_ticket(auth_client, auth_database)
    url = f"/api/events/{event['id']}/check-ins"
    assert (
        auth_client.post(url, json={"ticket_code": row["ticket_code"]}).status_code
        == 403
    )
    assert (
        auth_client.post(
            url,
            headers=headers(auth_client) | {"Origin": "http://evil.example"},
            json={"ticket_code": row["ticket_code"]},
        ).status_code
        == 403
    )
    for body in (
        {},
        {"ticket_code": None},
        {"ticket_code": 123},
        {"ticket_code": "7K4P\t9Q2M8RTA"},
    ):
        result = auth_client.post(url, headers=headers(auth_client), json=body)
        assert result.status_code == 422
        assert result.json()["error"]["code"] == "VALIDATION_ERROR"
        assert result.headers["cache-control"] == "no-store"
    missing = submit(auth_client, {"id": str(uuid4())}, row["ticket_code"])
    assert missing.json()["error"]["code"] == "EVENT_NOT_FOUND"
    for status, code in [
        ("DRAFT", "CHECKIN_NOT_OPEN"),
        ("CANCELLED", "EVENT_CANCELLED"),
    ]:
        with auth_database.begin() as conn:
            conn.execute(
                text("UPDATE events SET status = :status WHERE id = :id"),
                {"status": status, "id": event["id"]},
            )
        assert (
            submit(auth_client, event, row["ticket_code"]).json()["error"]["code"]
            == code
        )
    auth_client.cookies.clear()
    login(auth_client, "outsider@example.com")
    result = submit(auth_client, event, row["ticket_code"])
    assert result.status_code == 403
    assert result.json()["error"]["code"] == "EVENT_NOT_OWNER"
    auth_client.cookies.clear()
    assert submit(auth_client, event, row["ticket_code"]).status_code == 401


def test_other_event_code(auth_client, auth_database):
    _, event, row = fixture_ticket(auth_client, auth_database)
    from tests.integration.test_event_draft_edit import create

    other = create(auth_client)
    with auth_database.begin() as conn:
        conn.execute(
            text(
                "UPDATE events SET status = 'PUBLISHED', "
                "starts_at = :start, ends_at = :end WHERE id = :id"
            ),
            {
                "start": NOW + timedelta(hours=1),
                "end": NOW + timedelta(hours=2),
                "id": other["id"],
            },
        )
    result = submit(auth_client, other, row["ticket_code"])
    assert result.status_code == 404
    assert result.json()["error"]["code"] == "TICKET_NOT_FOUND"
    assert "participant" not in result.json()
    assert submit(auth_client, event, "234567892345").status_code == 404


def test_transaction_rollback(auth_client, auth_database, monkeypatch):
    owner, event, row = fixture_ticket(auth_client, auth_database)
    with Session(auth_database) as session:

        def fail():
            raise OperationalError("commit", {}, Exception("failure"))

        monkeypatch.setattr(session, "commit", fail)
        with pytest.raises(AppError) as error:
            checkin.check_in(
                session,
                FixedClock(NOW),
                owner,
                UUID(event["id"]),
                row["ticket_code"].replace("-", ""),
            )
        assert error.value.code == "SERVICE_UNAVAILABLE"
    with Session(auth_database) as session:
        assert session.get(Registration, UUID(row["id"])).checked_in_at is None
    assert submit(auth_client, event, row["ticket_code"]).status_code == 200


def test_parallel_checkin(auth_client, auth_database):
    owner, event, row = fixture_ticket(auth_client, auth_database)
    barrier = Barrier(2)

    def attempt():
        with Session(auth_database) as session:
            barrier.wait(timeout=10)
            try:
                result = checkin.check_in(
                    session,
                    FixedClock(NOW),
                    owner,
                    UUID(event["id"]),
                    row["ticket_code"].replace("-", ""),
                )
                return 200, result.status
            except AppError as error:
                return error.status, error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(results) == [(200, "checked_in"), (409, "TICKET_ALREADY_CHECKED_IN")]


@pytest.mark.parametrize("check_first", [True, False])
def test_cancel_checkin_both_lock_orders(
    auth_client, auth_database, monkeypatch, check_first
):
    owner, event, row = fixture_ticket(auth_client, auth_database)
    acquired, release, second_started = Signal(), Signal(), Signal()
    original_share = checkin.events.find_event_for_share
    original_update = service.events.find_event_for_update

    def held(original):
        def lock(session, event_id):
            saved = original(session, event_id)
            acquired.set()
            assert release.wait(timeout=10)
            return saved

        return lock

    monkeypatch.setattr(
        checkin.events,
        "find_event_for_share" if check_first else "find_event_for_update",
        held(original_share if check_first else original_update),
    )

    def attempt(is_check, second=False):
        with Session(auth_database) as session:
            session.execute(text("SET lock_timeout = '8s'"))
            if second:
                second_started.set()
            try:
                if is_check:
                    checkin.check_in(
                        session,
                        FixedClock(NOW),
                        owner,
                        UUID(event["id"]),
                        row["ticket_code"].replace("-", ""),
                    )
                else:
                    service.cancel_registration(
                        session,
                        FixedClock(NOW),
                        UUID(row["user_id"]),
                        UUID(event["id"]),
                    )
                return 200, "success"
            except AppError as error:
                return error.status, error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(attempt, check_first)
        assert acquired.wait(timeout=10)
        second = pool.submit(attempt, not check_first, True)
        assert second_started.wait(timeout=10)
        try:
            # Observe the second connection blocked on the first Event lock.
            from time import monotonic

            deadline = monotonic() + 5
            with auth_database.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                while not conn.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND cardinality(pg_blocking_pids(pid)) > 0)"
                    )
                ):
                    assert monotonic() < deadline, "second transaction did not block"
        finally:
            release.set()
        assert first.result(timeout=10) == (200, "success")
        assert second.result(timeout=10) == (
            (409, "TICKET_ALREADY_CHECKED_IN")
            if check_first
            else (404, "TICKET_NOT_FOUND")
        )


def test_cancelled_and_stale_codes(auth_client, auth_database):
    _, event, row = fixture_ticket(auth_client, auth_database)
    auth_client.post(
        "/api/auth/login",
        headers=headers(auth_client),
        json={"email": "participant@example.com", "password": "a long password"},
    )
    assert (
        auth_client.delete(
            f"/api/events/{event['id']}/registration", headers=headers(auth_client)
        ).status_code
        == 200
    )
    sign_in_owner(auth_client)
    assert submit(auth_client, event, row["ticket_code"]).status_code == 404
    auth_client.post(
        "/api/auth/login",
        headers=headers(auth_client),
        json={"email": "participant@example.com", "password": "a long password"},
    )
    new = post(auth_client, event).json()
    assert new["ticket_code"] != row["ticket_code"]
    sign_in_owner(auth_client)
    assert submit(auth_client, event, row["ticket_code"]).status_code == 404
    assert submit(auth_client, event, new["ticket_code"]).status_code == 200
