from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.integration.test_checkin import sign_in_owner, submit
from tests.integration.test_event_draft_edit import create, headers, login, patch
from tests.integration.test_event_registration import NOW, post, setup_event


def stats(client, event):
    return client.get(f"/api/events/{event['id']}/stats")


def assert_stats(client, event, capacity, confirmed, waitlist, checked_in, available):
    response = stats(client, event)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "event_id": event["id"],
        "capacity": capacity,
        "confirmed": confirmed,
        "waitlist": waitlist,
        "checked_in": checked_in,
        "available_slots": available,
    }


def test_empty_stats(auth_client, auth_database):
    _, event = setup_event(auth_client, auth_database, capacity=7)
    assert_stats(auth_client, event, 7, 0, 0, 0, 7)


def test_counts_after_registration_cancel_promotion_capacity_checkin(
    auth_client, auth_database
):
    _, event = setup_event(auth_client, auth_database)
    rows = []
    for index in range(3):
        auth_client.cookies.clear()
        login(auth_client, f"participant{index}@example.com")
        response = post(auth_client, event)
        assert response.status_code == 201
        rows.append(response.json())
    sign_in_owner(auth_client)
    assert_stats(auth_client, event, 1, 1, 2, 0, 0)

    # Cancellation excludes the cancelled row and promotes one waiter.
    assert (
        auth_client.post(
            "/api/auth/login",
            headers=headers(auth_client),
            json={"email": "participant0@example.com", "password": "a long password"},
        ).status_code
        == 200
    )
    assert (
        auth_client.delete(
            f"/api/events/{event['id']}/registration", headers=headers(auth_client)
        ).status_code
        == 200
    )
    sign_in_owner(auth_client)
    assert_stats(auth_client, event, 1, 1, 1, 0, 0)
    assert patch(auth_client, event["id"], {"capacity": 3}).status_code == 200
    assert_stats(auth_client, event, 3, 2, 0, 0, 1)

    with auth_database.begin() as conn:
        conn.execute(
            text("UPDATE events SET starts_at = :start, ends_at = :end WHERE id = :id"),
            {
                "start": NOW + timedelta(hours=1),
                "end": NOW + timedelta(hours=2),
                "id": event["id"],
            },
        )
        ticket = conn.scalar(
            text("SELECT ticket_code FROM registrations WHERE id = :id"),
            {"id": rows[1]["id"]},
        )
    assert submit(auth_client, event, ticket).status_code == 200
    assert_stats(auth_client, event, 3, 2, 0, 1, 1)


@pytest.mark.parametrize("lifecycle", ["DRAFT", "PUBLISHED", "FINISHED", "CANCELLED"])
def test_stats_access_lifecycle(auth_client, auth_database, lifecycle):
    login(auth_client)
    event = create(auth_client)
    if lifecycle != "DRAFT":
        with auth_database.begin() as conn:
            conn.execute(
                text(
                    "UPDATE events SET status = :status, starts_at = :start, "
                    "ends_at = :end WHERE id = :id"
                ),
                {
                    "status": "PUBLISHED" if lifecycle == "FINISHED" else lifecycle,
                    "start": NOW - timedelta(hours=1)
                    if lifecycle == "FINISHED"
                    else NOW + timedelta(hours=1),
                    "end": NOW if lifecycle == "FINISHED" else NOW + timedelta(hours=2),
                    "id": event["id"],
                },
            )
    response = stats(auth_client, event)
    assert response.headers["cache-control"] == "no-store"
    if lifecycle == "DRAFT":
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EVENT_NOT_PUBLISHED"
    else:
        assert_stats(auth_client, event, 25, 0, 0, 0, 25)
    auth_client.cookies.clear()
    login(auth_client, "outsider@example.com")
    response = stats(auth_client, event)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "EVENT_NOT_OWNER"
    assert response.headers["cache-control"] == "no-store"
    missing = stats(auth_client, {"id": str(uuid4())})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EVENT_NOT_FOUND"
    assert missing.headers["cache-control"] == "no-store"
    auth_client.cookies.clear()
    response = stats(auth_client, event)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.headers["cache-control"] == "no-store"
    invalid = auth_client.get("/api/events/invalid/stats")
    assert invalid.status_code in {401, 422}
    assert invalid.headers["cache-control"] == "no-store"


def test_checked_in_is_subset_of_confirmed(auth_client, auth_database):
    _, event = setup_event(auth_client, auth_database, capacity=3)
    for index in range(2):
        auth_client.cookies.clear()
        login(auth_client, f"participant{index}@example.com")
        assert post(auth_client, event).status_code == 201
    with auth_database.begin() as conn:
        conn.execute(
            text("UPDATE registrations SET checked_in_at = :now"), {"now": NOW}
        )
    sign_in_owner(auth_client)
    assert_stats(auth_client, event, 3, 2, 0, 2, 1)
    assert (
        auth_client.post(
            "/api/auth/login",
            headers=headers(auth_client),
            json={"email": "participant0@example.com", "password": "a long password"},
        ).status_code
        == 200
    )
    assert (
        auth_client.delete(
            f"/api/events/{event['id']}/registration", headers=headers(auth_client)
        ).status_code
        == 409
    )
    sign_in_owner(auth_client)
    assert_stats(auth_client, event, 3, 2, 0, 2, 1)


def test_stats_reads_committed_capacity_snapshot(auth_client, auth_database):
    owner, event = setup_event(auth_client, auth_database, capacity=1)
    # Read-only stats sees a complete committed snapshot while a capacity write
    # is pending, then the new snapshot even in a session holding an old Event.
    from app.events.models import Event
    from app.events.stats import get_owned_stats

    with Session(auth_database) as reader, auth_database.connect() as writer:
        cached = reader.get(Event, UUID(event["id"]))
        assert cached.capacity == 1
        writer.execute(
            text("UPDATE events SET capacity = 4 WHERE id = :id"), {"id": event["id"]}
        )
        before = get_owned_stats(reader, UUID(owner), UUID(event["id"]))
        assert (before.capacity, before.available_slots) == (1, 1)
        writer.commit()
        after = get_owned_stats(reader, UUID(owner), UUID(event["id"]))
        assert (after.capacity, after.available_slots) == (4, 4)
