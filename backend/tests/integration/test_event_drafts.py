from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

BODY = {
    "title": "  Community meetup  ",
    "description": "<b>Plain text description</b>",
    "starts_at": "2026-10-10T15:00:00+03:00",
    "ends_at": "2026-10-10T17:00:00+03:00",
    "timezone": "Europe/Moscow",
    "capacity": 25,
}


def headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    return {"Origin": "http://localhost:8080", "X-CSRF-Token": token}


def login(client: TestClient, email: str = "owner@example.com") -> str:
    h = headers(client)
    body = {"email": email, "password": "a long password"}
    created = client.post("/api/auth/register", json=body, headers=h)
    assert created.status_code == 201
    assert client.post("/api/auth/login", json=body, headers=h).status_code == 200
    return created.json()["id"]


def create(client: TestClient, **changes):
    return client.post("/api/events", json=BODY | changes, headers=headers(client))


def test_create_draft_persists_normalized_contract_and_utc_clock(
    auth_client, auth_database
):
    owner = login(auth_client)
    r = create(auth_client)
    assert r.status_code == 201
    body = r.json()
    UUID(body["id"])
    assert body["owner_id"] == owner
    assert body["title"] == "Community meetup"
    assert body["description"] == BODY["description"]
    assert body["status"] == "DRAFT"
    assert body["published_at"] is body["cancelled_at"] is None
    assert body["starts_at"] == "2026-10-10T12:00:00Z"
    assert body["ends_at"] == "2026-10-10T14:00:00Z"
    assert (
        body["created_at"]
        == body["updated_at"]
        == body["schedule_updated_at"]
        == "2026-10-04T12:00:00Z"
    )
    import re

    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", body["slug"])
    assert auth_client.get(f"/api/events/{body['id']}").json() == body
    with auth_database.connect() as connection:
        row = (
            connection.execute(
                text("SELECT * FROM events WHERE id = :id"), {"id": body["id"]}
            )
            .mappings()
            .one()
        )
        assert row["capacity"] == 25
        assert row["owner_id"] == UUID(owner)
        assert row["starts_at"] == datetime(2026, 10, 10, 12, tzinfo=UTC)
    assert "password" not in r.text


@pytest.mark.parametrize(
    "patch",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"description": ""},
        {"description": "x" * 10001},
        {"capacity": 0},
        {"capacity": -1},
        {"capacity": True},
        {"capacity": 1.5},
        {"capacity": 2147483648},
        {"title": "bad\x00title"},
        {"description": "bad\x00description"},
        {"starts_at": "9999-12-31T23:00:00-02:00"},
        {"ends_at": "9999-12-31T23:00:00-02:00"},
        {"timezone": "Not/AZone"},
        {"timezone": "../etc/passwd"},
        {"starts_at": "2026-10-04T12:00:00Z"},
        {"starts_at": "2026-10-04T11:59:59Z"},
        {"starts_at": "2026-10-10T12:00:00"},
        {"starts_at": 1791633600},
        {"ends_at": "2026-10-10T12:00:00Z"},
        {"ends_at": "2026-10-10T11:59:59Z"},
        {"owner_id": str(uuid4())},
        {"status": "PUBLISHED"},
        {"slug": "mine"},
        {"title": None},
    ],
)
def test_invalid_event_never_creates_a_row(auth_client, auth_database, patch):
    login(auth_client)
    r = create(auth_client, **patch)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == 0


@pytest.mark.parametrize(
    "title,description",
    [("я", "я"), ("я" * 200, "я" * 10000)],
    ids=["minimum", "maximum"],
)
def test_text_character_boundaries_are_accepted(auth_client, title, description):
    login(auth_client)
    r = create(auth_client, title=title, description=description)
    assert r.status_code == 201
    assert r.json()["title"] == title


def test_mine_filters_owners_and_orders_equal_created_at_by_id(auth_client):
    login(auth_client)
    first = create(auth_client).json()
    second = create(auth_client).json()
    assert first["slug"] != second["slug"]
    mine = auth_client.get("/api/events/mine")
    assert mine.status_code == 200
    assert [r["id"] for r in mine.json()] == sorted(
        [first["id"], second["id"]], reverse=True
    )
    assert set(mine.json()[0]) == {
        "id",
        "title",
        "slug",
        "starts_at",
        "ends_at",
        "timezone",
        "capacity",
        "status",
    }
    auth_client.cookies.clear()
    login(auth_client, "other@example.com")
    assert auth_client.get("/api/events/mine").json() == []
    assert create(auth_client, title="Other event").status_code == 201
    assert len(auth_client.get("/api/events/mine").json()) == 1
    foreign = auth_client.get(f"/api/events/{first['id']}")
    assert foreign.status_code == 403
    assert foreign.json()["error"]["code"] == "EVENT_NOT_OWNER"
    missing = auth_client.get(f"/api/events/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EVENT_NOT_FOUND"


def test_auth_and_csrf_failures_do_not_mutate_events(auth_client, auth_database):
    assert auth_client.get("/api/events/mine").status_code == 401
    assert create(auth_client).status_code == 401
    login(auth_client)
    for h in [
        {},
        {"Origin": "null"},
        {"Origin": "http://localhost:8080", "X-CSRF-Token": "wrong"},
    ]:
        r = auth_client.post("/api/events", json=BODY, headers=h)
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "CSRF_INVALID"
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == 0


def test_event_migration_checks_fk_unique_and_timestamp_types(
    auth_client, auth_database
):
    login(auth_client)
    r = create(auth_client)
    assert r.status_code == 201
    event_id = r.json()["id"]
    schema = inspect(auth_database)
    columns = {c["name"]: c for c in schema.get_columns("events")}
    assert set(columns) == {
        "id",
        "owner_id",
        "title",
        "description",
        "slug",
        "starts_at",
        "ends_at",
        "timezone",
        "capacity",
        "status",
        "schedule_updated_at",
        "published_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    }
    for field in [
        "starts_at",
        "ends_at",
        "schedule_updated_at",
        "published_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    ]:
        assert columns[field]["type"].timezone
    assert {k for k, c in columns.items() if c["nullable"]} == {
        "published_at",
        "cancelled_at",
    }
    for sql, params in [
        ("UPDATE events SET capacity = 0 WHERE id = :id", {}),
        ("UPDATE events SET ends_at = starts_at WHERE id = :id", {}),
        ("UPDATE events SET owner_id = :owner WHERE id = :id", {"owner": uuid4()}),
        ("UPDATE events SET status = 'FINISHED' WHERE id = :id", {}),
    ]:
        with pytest.raises(IntegrityError), auth_database.begin() as connection:
            connection.execute(text(sql), {"id": event_id} | params)
    second = create(auth_client).json()
    with pytest.raises(IntegrityError), auth_database.begin() as connection:
        connection.execute(
            text("UPDATE events SET slug = :slug WHERE id = :id"),
            {"id": second["id"], "slug": r.json()["slug"]},
        )


def test_slug_collision_retries_without_losing_previous_event(
    auth_client, auth_database, monkeypatch
):
    login(auth_client)
    first = create(auth_client).json()
    from app.events import service

    slugs = iter([first["slug"], "community-meetup-new-random-suffix"])
    monkeypatch.setattr(service, "generate_slug", lambda title: next(slugs))
    second = create(auth_client)
    assert second.status_code == 201
    assert second.json()["slug"] == "community-meetup-new-random-suffix"
    assert auth_client.get(f"/api/events/{first['id']}").json() == first
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == 2
