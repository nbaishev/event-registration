from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

BODY = {
    "title": "Community meetup",
    "description": "Plain text description",
    "starts_at": "2026-10-10T12:00:00Z",
    "ends_at": "2026-10-10T14:00:00Z",
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


def create(client: TestClient) -> dict:
    response = client.post("/api/events", json=BODY, headers=headers(client))
    assert response.status_code == 201
    return response.json()


def patch(client: TestClient, event_id: str, body: dict):
    return client.patch(f"/api/events/{event_id}", json=body, headers=headers(client))


def test_partial_text_edit_preserves_identity_schedule_slug_and_owner(auth_client):
    owner_id = login(auth_client)
    before = create(auth_client)
    edited = patch(
        auth_client,
        before["id"],
        {"title": "  Updated meetup  ", "description": "Revised plain text"},
    )
    assert edited.status_code == 200
    after = edited.json()
    assert after["title"] == "Updated meetup"
    assert after["description"] == "Revised plain text"
    assert after["id"] == before["id"]
    assert after["owner_id"] == owner_id
    assert after["status"] == "DRAFT"
    assert after["slug"] == before["slug"]
    assert (
        after["starts_at"],
        after["ends_at"],
        after["timezone"],
        after["capacity"],
    ) == (
        before["starts_at"],
        before["ends_at"],
        before["timezone"],
        before["capacity"],
    )
    assert auth_client.get(f"/api/events/{before['id']}").json() == after


def test_schedule_change_normalizes_utc_and_uses_clock_only_for_schedule(auth_client):
    from app.common.clock import FixedClock, get_clock
    from app.main import app

    login(auth_client)
    before = create(auth_client)
    now = datetime(2026, 10, 5, 12, tzinfo=UTC)
    app.dependency_overrides[get_clock] = lambda: FixedClock(now)
    assert (
        auth_client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "a long password"},
            headers=headers(auth_client),
        ).status_code
        == 200
    )
    text_only = patch(auth_client, before["id"], {"title": "New title"}).json()
    assert text_only["schedule_updated_at"] == before["schedule_updated_at"]
    assert text_only["updated_at"] == "2026-10-05T12:00:00Z"

    capacity_only = patch(auth_client, before["id"], {"capacity": 30})
    assert capacity_only.status_code == 200
    assert capacity_only.json()["schedule_updated_at"] == before["schedule_updated_at"]

    changed = patch(
        auth_client,
        before["id"],
        {
            "starts_at": "2026-10-11T18:00:00+06:00",
            "ends_at": "2026-10-11T20:00:00+06:00",
            "timezone": "Asia/Almaty",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["starts_at"] == "2026-10-11T12:00:00Z"
    assert changed.json()["schedule_updated_at"] == "2026-10-05T12:00:00Z"
    assert changed.json()["ends_at"] == "2026-10-11T14:00:00Z"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"regenerate_slug": False},
        {"regenerate_slug": None},
        {"title": None},
        {"description": None},
        {"starts_at": None},
        {"ends_at": None},
        {"timezone": None},
        {"capacity": None},
        {"title": "   "},
        {"title": "x" * 201},
        {"description": ""},
        {"description": "x" * 10001},
        {"capacity": 0},
        {"capacity": True},
        {"capacity": 2147483648},
        {"timezone": "Not/AZone"},
        {"starts_at": "2026-10-10T12:00:00"},
        {"ends_at": 1791633600},
        {"owner_id": str(uuid4())},
        {"status": "PUBLISHED"},
        {"slug": "forged"},
        {"published_at": "2026-10-04T12:00:00Z"},
        {"title": "bad\x00title"},
    ],
    ids=[
        "empty",
        "no-op-slug",
        "null-regenerate-slug",
        "null-title",
        "null-description",
        "null-start",
        "null-end",
        "null-timezone",
        "null-capacity",
        "blank-title",
        "long-title",
        "empty-description",
        "long-description",
        "zero-capacity",
        "bool-capacity",
        "int-overflow",
        "invalid-zone",
        "naive-start",
        "numeric-end",
        "owner",
        "status",
        "slug",
        "published-at",
        "nul-title",
    ],
)
def test_invalid_patch_is_422_and_leaves_event_unchanged(auth_client, body):
    login(auth_client)
    before = create(auth_client)
    response = patch(auth_client, before["id"], body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert auth_client.get(f"/api/events/{before['id']}").json() == before


@pytest.mark.parametrize(
    "body",
    [
        {"starts_at": "2026-10-10T14:00:00Z"},
        {"ends_at": "2026-10-10T11:59:59Z"},
    ],
    ids=["equal-start-end", "end-before-start"],
)
def test_patch_validates_merged_interval_atomically(auth_client, body):
    login(auth_client)
    before = create(auth_client)
    response = patch(auth_client, before["id"], body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert auth_client.get(f"/api/events/{before['id']}").json() == before


def test_started_event_rejects_schedule_and_capacity_changes_but_allows_text(
    auth_client,
):
    from app.common.clock import FixedClock, get_clock
    from app.main import app

    login(auth_client)
    before = create(auth_client)
    app.dependency_overrides[get_clock] = lambda: FixedClock(
        datetime(2026, 10, 10, 12, tzinfo=UTC)
    )
    assert (
        auth_client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "a long password"},
            headers=headers(auth_client),
        ).status_code
        == 200
    )
    for body in [
        {"starts_at": "2026-10-11T12:00:00Z"},
        {"ends_at": "2026-10-11T14:00:00Z"},
        {"timezone": "Asia/Almaty"},
        {"capacity": 50},
    ]:
        response = patch(auth_client, before["id"], body)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EVENT_ALREADY_STARTED"
        assert auth_client.get(f"/api/events/{before['id']}").json() == before
    text_edit = patch(auth_client, before["id"], {"description": "Still editable"})
    assert text_edit.status_code == 200
    assert text_edit.json()["description"] == "Still editable"


def test_owner_missing_and_auth_contract(auth_client):
    login(auth_client)
    event = create(auth_client)
    auth_client.cookies.clear()
    assert patch(auth_client, event["id"], {"title": "No auth"}).status_code == 401
    login(auth_client, "other@example.com")
    foreign = patch(auth_client, event["id"], {"title": "Other owner"})
    assert foreign.status_code == 403
    assert foreign.json()["error"]["code"] == "EVENT_NOT_OWNER"
    missing = patch(auth_client, str(uuid4()), {"title": "Missing"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EVENT_NOT_FOUND"


@pytest.mark.parametrize(
    "status,expected",
    [("PUBLISHED", "EVENT_NOT_EDITABLE"), ("CANCELLED", "EVENT_CANCELLED")],
)
def test_patch_rejects_non_draft_without_mutation(
    auth_client, auth_database, status, expected
):
    login(auth_client)
    event = create(auth_client)
    with auth_database.begin() as connection:
        connection.execute(
            text("UPDATE events SET status = :status WHERE id = :id"),
            {"status": status, "id": event["id"]},
        )
    before = auth_client.get(f"/api/events/{event['id']}").json()
    response = patch(auth_client, event["id"], {"title": "Changed"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == expected
    assert auth_client.get(f"/api/events/{event['id']}").json() == before


def test_title_change_keeps_slug_and_explicit_regeneration_retries_collisions(
    auth_client, monkeypatch
):
    login(auth_client)
    original = create(auth_client)
    titled = patch(auth_client, original["id"], {"title": "A different title"})
    assert titled.status_code == 200
    assert titled.json()["slug"] == original["slug"]

    from app.events import service

    other = create(auth_client)
    candidates = iter([other["slug"], "a-different-title-random-suffix"])
    monkeypatch.setattr(service, "generate_slug", lambda title: next(candidates))
    regenerated = patch(auth_client, original["id"], {"regenerate_slug": True})
    assert regenerated.status_code == 200
    assert regenerated.json()["slug"] == "a-different-title-random-suffix"
    assert auth_client.get(f"/api/events/{other['id']}").json() == other


def test_slug_retry_exhaustion_rolls_back_other_fields(auth_client, monkeypatch):
    login(auth_client)
    event = create(auth_client)
    from app.events import service

    monkeypatch.setattr(service, "generate_slug", lambda title: event["slug"])
    failed = patch(
        auth_client,
        event["id"],
        {"title": "Would partially save", "regenerate_slug": True},
    )
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert auth_client.get(f"/api/events/{event['id']}").json() == event


def test_competing_partial_patches_keep_both_fields_on_postgres(auth_client):
    login(auth_client)
    event = create(auth_client)
    barrier = Barrier(2)

    def update(changes: dict) -> None:
        barrier.wait(timeout=10)
        response = auth_client.patch(
            f"/api/events/{event['id']}",
            json=changes,
            headers=headers(auth_client),
        )
        assert response.status_code == 200, response.text

    with ThreadPoolExecutor(max_workers=2) as pool:
        title = pool.submit(update, {"title": "Concurrent title"})
        description = pool.submit(update, {"description": "Concurrent description"})
        title.result(timeout=10)
        description.result(timeout=10)

    after = auth_client.get(f"/api/events/{event['id']}").json()
    assert after["title"] == "Concurrent title"
    assert after["description"] == "Concurrent description"
