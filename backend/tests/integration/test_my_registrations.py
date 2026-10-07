from datetime import timedelta

from sqlalchemy import text

from app.common.clock import FixedClock, get_clock
from app.main import app
from tests.integration.test_event_registration import NOW
from tests.integration.test_registration_cancel import delete, participants, sign_in

URL = "/api/me/registrations"


def test_list_isolation_and_cancelled_history(auth_client, auth_database):
    event, rows = participants(auth_client, auth_database, 2)
    sign_in(auth_client, 0)
    response = auth_client.get(URL)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert [item["registration"] for item in response.json()] == [rows[0]]
    assert rows[1]["user_id"] not in response.text
    cancelled = delete(auth_client, event).json()
    assert auth_client.get(URL).json()[0]["registration"] == cancelled
    sign_in(auth_client, 1)
    assert auth_client.get(URL).json()[0]["registration"]["status"] == "CONFIRMED"


def test_order_and_global_event_waitlist_position(auth_client, auth_database):
    event, rows = participants(auth_client, auth_database, 3)
    sign_in(auth_client, 2)
    with auth_database.begin() as conn:
        conn.execute(
            text("UPDATE registrations SET waitlisted_at = :time WHERE id = :id"),
            {"time": NOW + timedelta(seconds=1), "id": rows[2]["id"]},
        )
    result = auth_client.get(URL)
    assert result.status_code == 200
    assert result.json()[0]["registration"]["waitlist_position"] == 2
    # Add two more events for the same participant, keeping equal update timestamps.
    with auth_database.begin() as conn:
        for event_id, registration_id, updated in [
            (
                "00000000-0000-4000-8000-000000000001",
                "00000000-0000-4000-8000-000000000001",
                NOW + timedelta(minutes=1),
            ),
            (
                "00000000-0000-4000-8000-000000000002",
                "00000000-0000-4000-8000-000000000002",
                NOW + timedelta(minutes=1),
            ),
        ]:
            conn.execute(
                text(
                    "INSERT INTO events (id,owner_id,title,description,slug,"
                    "starts_at,ends_at,timezone,capacity,status,schedule_updated_at,"
                    "published_at,cancelled_at,created_at,updated_at) "
                    "SELECT :new_id, owner_id, title, description, :slug, "
                    "starts_at, ends_at, timezone, capacity, status, "
                    "schedule_updated_at, published_at, cancelled_at, "
                    "created_at, updated_at FROM events WHERE id = :id"
                ),
                {"new_id": event_id, "slug": event_id, "id": event["id"]},
            )
            conn.execute(
                text(
                    "INSERT INTO registrations (id,event_id,user_id,status,"
                    "waitlisted_at,created_at,updated_at) "
                    "VALUES (:id,:event,:user,'WAITLIST',:now,:now,:updated)"
                ),
                {
                    "id": registration_id,
                    "event": event_id,
                    "user": rows[2]["user_id"],
                    "now": NOW,
                    "updated": updated,
                },
            )
    items = auth_client.get(URL).json()
    assert [item["registration"]["id"] for item in items] == [
        "00000000-0000-4000-8000-000000000002",
        "00000000-0000-4000-8000-000000000001",
        rows[2]["id"],
    ]
    assert [item["registration"]["waitlist_position"] for item in items] == [1, 1, 2]


def test_event_summary_privacy_and_finished(auth_client, auth_database):
    event, _ = participants(auth_client, auth_database, 1)
    app.dependency_overrides[get_clock] = lambda: FixedClock(NOW)
    with auth_database.begin() as conn:
        conn.execute(
            text(
                "UPDATE events SET starts_at = :starts, ends_at = :ends WHERE id = :id"
            ),
            {"starts": NOW - timedelta(hours=1), "ends": NOW, "id": event["id"]},
        )
    response = auth_client.get(URL)
    assert response.status_code == 200
    summary = response.json()[0]["event"]
    assert set(summary) == {
        "id",
        "title",
        "slug",
        "starts_at",
        "ends_at",
        "timezone",
        "status",
    }
    assert summary["status"] == "FINISHED"
    with auth_database.begin() as conn:
        assert (
            conn.scalar(
                text("SELECT status FROM events WHERE id = :id"), {"id": event["id"]}
            )
            == "PUBLISHED"
        )
        conn.execute(
            text("UPDATE events SET status = 'DRAFT' WHERE id = :id"),
            {"id": event["id"]},
        )
    assert auth_client.get(URL).json() == []


def test_empty_and_auth_required(auth_client, auth_database):
    participants(auth_client, auth_database, 0)
    response = auth_client.get(URL)
    assert response.status_code == 200
    assert response.json() == []
    auth_client.cookies.clear()
    response = auth_client.get(URL)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
