from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event as Signal
from time import monotonic
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.clock import FixedClock
from app.common.errors import AppError
from app.events import service
from app.events.models import Event
from app.registrations.models import Registration, RegistrationStatus
from tests.integration.test_event_draft_edit import create, headers, login

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def delete(client, event_id):
    return client.delete(f"/api/events/{event_id}", headers=headers(client))


def test_delete_authorization_and_repeat(auth_client, auth_database):
    login(auth_client)
    event = create(auth_client)
    url = f"/api/events/{event['id']}"
    auth_client.cookies.clear()
    assert delete(auth_client, event["id"]).status_code == 401
    login(auth_client, "other@example.com")
    foreign = delete(auth_client, event["id"])
    assert foreign.status_code == 403
    assert foreign.json()["error"]["code"] == "EVENT_NOT_OWNER"
    missing = delete(auth_client, str(uuid4()))
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EVENT_NOT_FOUND"
    auth_client.post(
        "/api/auth/login",
        headers=headers(auth_client),
        json={"email": "owner@example.com", "password": "a long password"},
    )
    assert auth_client.delete(url).status_code == 403
    h = headers(auth_client)
    assert (
        auth_client.delete(
            url, headers=h | {"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        auth_client.delete(url, headers=h | {"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    assert auth_client.get(url).json() == event
    response = delete(auth_client, event["id"])
    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"
    with Session(auth_database) as session:
        assert session.get(Event, UUID(event["id"])) is None
    assert auth_client.get("/api/events/mine").json() == []
    assert auth_client.get(url).status_code == 404
    repeat = delete(auth_client, event["id"])
    assert repeat.status_code == 404
    assert repeat.json()["error"]["code"] == "EVENT_NOT_FOUND"


@pytest.mark.parametrize("status", ["PUBLISHED", "CANCELLED"])
def test_non_draft_cannot_be_deleted(auth_client, auth_database, status):
    login(auth_client)
    event = create(auth_client)
    with auth_database.begin() as connection:
        connection.execute(
            text("UPDATE events SET status = :status WHERE id = :id"),
            {"id": event["id"], "status": status},
        )
    before = auth_client.get(f"/api/events/{event['id']}").json()
    response = delete(auth_client, event["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_NOT_DELETABLE"
    assert auth_client.get(f"/api/events/{event['id']}").json() == before


@pytest.mark.parametrize("status", list(RegistrationStatus))
def test_any_registration_prevents_draft_delete(auth_client, auth_database, status):
    owner = UUID(login(auth_client))
    event = create(auth_client)
    row_id = uuid4()
    with Session(auth_database) as session:
        session.add(
            Registration(
                id=row_id,
                event_id=UUID(event["id"]),
                user_id=owner,
                status=status,
                confirmed_at=NOW if status == RegistrationStatus.CONFIRMED else None,
                waitlisted_at=NOW if status == RegistrationStatus.WAITLIST else None,
                cancelled_at=NOW if status == RegistrationStatus.CANCELLED else None,
                ticket_code="ABCDEFGHJK"
                if status == RegistrationStatus.CONFIRMED
                else None,
                ticket_issued_at=NOW
                if status == RegistrationStatus.CONFIRMED
                else None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.commit()
    from app.registrations.repository import count_confirmed, count_registrations

    with Session(auth_database) as session:
        assert count_registrations(session, UUID(event["id"])) == 1
        assert count_confirmed(session, UUID(event["id"])) == int(
            status == RegistrationStatus.CONFIRMED
        )
        assert count_registrations(session, uuid4()) == 0
    response = delete(auth_client, event["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_NOT_DELETABLE"
    assert auth_client.get(f"/api/events/{event['id']}").json() == event
    with Session(auth_database) as session:
        assert session.get(Registration, row_id).status == status
        # Existing FK prevents orphan/cascade deletion even outside the use-case.
        with pytest.raises(IntegrityError):
            session.delete(session.get(Event, UUID(event["id"])))
            session.commit()
        session.rollback()
        assert session.get(Registration, row_id) is not None


@pytest.mark.parametrize("first", ["delete", "publish"])
def test_delete_publish_lock_orders(auth_client, auth_database, first):
    owner_id = UUID(login(auth_client))
    event_id = UUID(create(auth_client)["id"])
    ready = Signal()
    pids = []
    with Session(auth_database) as locked:
        assert (
            locked.scalar(select(Event).where(Event.id == event_id).with_for_update())
            is not None
        )
        blocker = locked.scalar(text("SELECT pg_backend_pid()"))

        def second():
            with Session(auth_database) as session:
                pids.append(session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                with pytest.raises(AppError) as failure:
                    if first == "delete":
                        service.publish_owned_event(
                            session, FixedClock(NOW), owner_id, event_id
                        )
                    else:
                        service.delete_owned_event(session, owner_id, event_id)
                assert (failure.value.status, failure.value.code) == (
                    (404, "EVENT_NOT_FOUND")
                    if first == "delete"
                    else (409, "EVENT_NOT_DELETABLE")
                )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(second)
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
                        pytest.fail("Second operation did not wait on Event lock")
                if first == "delete":
                    service.delete_owned_event(locked, owner_id, event_id)
                else:
                    assert (
                        service.publish_owned_event(
                            locked, FixedClock(NOW), owner_id, event_id
                        ).status
                        == "PUBLISHED"
                    )
            finally:
                locked.rollback()
            future.result(timeout=5)
    with Session(auth_database) as session:
        saved = session.get(Event, event_id)
        if first == "delete":
            assert saved is None
        else:
            assert saved.status == "PUBLISHED"
