from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.common.clock import FixedClock, get_clock
from app.common.errors import AppError
from app.main import app
from app.registrations import service
from app.registrations.models import Registration
from tests.integration.test_event_draft_edit import headers, login
from tests.integration.test_event_registration import NOW, post, setup_event


def delete(client, event):
    return client.delete(
        f"/api/events/{event['id']}/registration", headers=headers(client)
    )


def participants(client, db, count=3):
    _, event = setup_event(client, db)
    rows = []
    for index in range(count):
        client.cookies.clear()
        login(client, f"p{index}@example.com")
        rows.append(post(client, event).json())
    return event, rows


def sign_in(client, index):
    assert (
        client.post(
            "/api/auth/login",
            headers=headers(client),
            json={"email": f"p{index}@example.com", "password": "a long password"},
        ).status_code
        == 200
    )


def test_cancel_promotes_and_reregisters(auth_client, auth_database):
    event, rows = participants(auth_client, auth_database, 2)
    sign_in(auth_client, 0)
    original = rows[0]
    result = delete(auth_client, event)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["status"] == "CANCELLED"
    assert result.json()["ticket_code"] is None
    assert delete(auth_client, event).status_code == 404
    later = NOW + timedelta(minutes=1)
    app.dependency_overrides[get_clock] = lambda: FixedClock(later)
    waiting = post(auth_client, event).json()
    assert waiting["id"] == original["id"]
    assert waiting["status"] == "WAITLIST"
    sign_in(auth_client, 1)
    promoted = auth_client.get(f"/api/events/{event['id']}/my-registration").json()
    assert promoted["status"] == "CONFIRMED"
    assert promoted["ticket_code"] != original["ticket_code"]
    assert delete(auth_client, event).status_code == 200
    sign_in(auth_client, 0)
    promoted_again = auth_client.get(
        f"/api/events/{event['id']}/my-registration"
    ).json()
    assert promoted_again["status"] == "CONFIRMED"
    assert promoted_again["ticket_code"] != original["ticket_code"]
    assert delete(auth_client, event).status_code == 200
    reactivated = post(auth_client, event).json()
    assert reactivated["id"] == original["id"]
    assert reactivated["status"] == "CONFIRMED"
    assert reactivated["ticket_code"] != promoted_again["ticket_code"]


def test_waitlist_cancel_does_not_promote(auth_client, auth_database):
    event, rows = participants(auth_client, auth_database)
    with Session(auth_database) as session:
        waiting = session.scalars(
            select(Registration)
            .where(Registration.status == "WAITLIST")
            .order_by(Registration.id)
        ).all()
        first_user = waiting[0].user_id
    index = next(i for i, r in enumerate(rows) if r["user_id"] == str(first_user))
    with auth_database.begin() as conn:
        conn.execute(
            text("UPDATE events SET capacity = 2 WHERE id = :id"), {"id": event["id"]}
        )
    sign_in(auth_client, index)
    assert delete(auth_client, event).json()["status"] == "CANCELLED"
    sign_in(auth_client, 3 - index)
    assert (
        auth_client.get(f"/api/events/{event['id']}/my-registration").json()[
            "waitlist_position"
        ]
        == 1
    )
    with auth_database.connect() as conn:
        assert conn.scalar(
            text("SELECT ticket_code FROM registrations WHERE id = :id"),
            {"id": rows[0]["id"]},
        ) == rows[0]["ticket_code"].replace("-", "")


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
def test_event_errors_precede_missing_registration(
    auth_client, auth_database, change, code, status
):
    _, event = setup_event(auth_client, auth_database)
    auth_client.cookies.clear()
    login(auth_client, "other@example.com")
    with auth_database.begin() as conn:
        conn.execute(
            text(f"UPDATE events SET {change} WHERE id = :id"), {"id": event["id"]}
        )
    result = delete(auth_client, event)
    assert result.status_code == status
    assert result.json()["error"]["code"] == code


def test_checked_in_guard_and_security(auth_client, auth_database):
    event, rows = participants(auth_client, auth_database, 1)
    url = f"/api/events/{event['id']}/registration"
    assert auth_client.delete(url).status_code == 403
    assert (
        auth_client.delete(
            url, headers=headers(auth_client) | {"Origin": "http://evil.example"}
        ).status_code
        == 403
    )
    with auth_database.begin() as conn:
        conn.execute(
            text("UPDATE registrations SET checked_in_at = :now WHERE id = :id"),
            {"now": NOW, "id": rows[0]["id"]},
        )
    assert (
        delete(auth_client, event).json()["error"]["code"]
        == "TICKET_ALREADY_CHECKED_IN"
    )
    auth_client.cookies.clear()
    assert delete(auth_client, event).status_code == 401


@pytest.mark.parametrize("race", [False, True])
def test_double_cancel_and_register_race(auth_client, auth_database, race):
    event, rows = participants(auth_client, auth_database, 2)
    auth_client.cookies.clear()
    newcomer = UUID(login(auth_client, "new@example.com"))
    barrier = Barrier(2)

    def attempt(register):
        with Session(auth_database) as session:
            barrier.wait(timeout=5)
            try:
                if register:
                    return 201, service.register_for_event(
                        session, FixedClock(NOW), newcomer, UUID(event["id"])
                    ).status
                return 200, service.cancel_registration(
                    session,
                    FixedClock(NOW),
                    UUID(rows[0]["user_id"]),
                    UUID(event["id"]),
                ).status
            except AppError as error:
                return error.status, error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            f.result(timeout=10)
            for f in [pool.submit(attempt, False), pool.submit(attempt, race)]
        ]
    assert sorted(code for code, _ in results) == ([200, 201] if race else [200, 404])
    with auth_database.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT count(*) FROM registrations WHERE status = 'CONFIRMED'")
            )
            == 1
        )
        assert conn.scalar(
            text("SELECT count(*) FROM registrations WHERE status = 'WAITLIST'")
        ) == (1 if race else 0)
