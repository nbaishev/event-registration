from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.common.clock import FixedClock, get_clock
from app.main import app
from tests.integration.test_event_draft_edit import create, headers, login, patch


def publish(client, event_id):
    return client.post(f"/api/events/{event_id}/publish", headers=headers(client))


def test_publish_public_contract_and_immutable_slug(auth_client):
    login(auth_client)
    before = create(auth_client)
    url = f"/api/public/events/{before['slug']}"
    assert auth_client.get(url).status_code == 404
    app.dependency_overrides[get_clock] = lambda: FixedClock(
        datetime.fromisoformat("2026-10-04T12:00:01+00:00")
    )
    response = publish(auth_client, before["id"])
    assert response.status_code == 200
    saved = response.json()
    assert saved["status"] == "PUBLISHED"
    assert saved["slug"] == before["slug"]
    assert (
        saved["published_at"] == saved["schedule_updated_at"] == "2026-10-04T12:00:01Z"
    )
    app.dependency_overrides[get_clock] = lambda: FixedClock(
        datetime.fromisoformat("2026-10-04T12:00:02+00:00")
    )
    assert publish(auth_client, before["id"]).status_code == 409
    assert auth_client.get(f"/api/events/{before['id']}").json() == saved
    assert (
        patch(auth_client, before["id"], {"regenerate_slug": True}).status_code == 409
    )
    auth_client.cookies.clear()
    public = auth_client.get(url)
    assert public.status_code == 200
    assert set(public.json()) == {
        "id",
        "title",
        "description",
        "slug",
        "starts_at",
        "ends_at",
        "timezone",
        "capacity",
        "status",
    }
    assert public.json()["status"] == "PUBLISHED"
    assert (
        auth_client.get("/api/public/events/unknown").json()["error"]["code"]
        == "EVENT_NOT_FOUND"
    )


@pytest.mark.parametrize(
    "change",
    [
        "timezone = 'invalid/zone'",
        "status = 'CANCELLED'",
        "starts_at = '2026-10-04T12:00:00Z'",
    ],
)
def test_unpublishable_event_no_mutation(auth_client, auth_database, change):
    login(auth_client)
    event = create(auth_client)
    with auth_database.begin() as db:
        db.execute(
            text(f"UPDATE events SET {change} WHERE id = :id"), {"id": event["id"]}
        )
    before = auth_client.get(f"/api/events/{event['id']}").json()
    response = publish(auth_client, event["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_NOT_PUBLISHABLE"
    assert auth_client.get(f"/api/events/{event['id']}").json() == before


@pytest.mark.parametrize(
    "now,status",
    [
        ("2026-10-10T13:59:59+00:00", "PUBLISHED"),
        ("2026-10-10T14:00:00+00:00", "FINISHED"),
        ("2026-10-10T14:00:01+00:00", "FINISHED"),
    ],
)
def test_effective_finished_boundary(auth_client, auth_database, now, status):
    login(auth_client)
    event = create(auth_client)
    assert publish(auth_client, event["id"]).status_code == 200
    app.dependency_overrides[get_clock] = lambda: FixedClock(
        datetime.fromisoformat(now)
    )
    assert (
        auth_client.get(f"/api/public/events/{event['slug']}").json()["status"]
        == status
    )
    with auth_database.connect() as db:
        assert (
            db.scalar(
                text("SELECT status FROM events WHERE id = :id"), {"id": event["id"]}
            )
            == "PUBLISHED"
        )


def test_cancelled_public_and_publish_authorization(auth_client, auth_database):
    login(auth_client)
    event = create(auth_client)
    with auth_database.begin() as db:
        db.execute(
            text("UPDATE events SET status = 'CANCELLED' WHERE id = :id"),
            {"id": event["id"]},
        )
    auth_client.cookies.clear()
    assert (
        auth_client.get(f"/api/public/events/{event['slug']}").json()["status"]
        == "CANCELLED"
    )
    assert publish(auth_client, event["id"]).status_code == 401
    login(auth_client, "other@example.com")
    assert (
        publish(auth_client, event["id"]).json()["error"]["code"] == "EVENT_NOT_OWNER"
    )
    assert publish(auth_client, str(uuid4())).status_code == 404
    assert auth_client.post(f"/api/events/{event['id']}/publish").status_code == 403


def test_concurrent_publish_and_patch_are_serialized(auth_client):
    login(auth_client)
    event = create(auth_client)
    h = headers(auth_client)
    barrier = Barrier(2)

    def do_publish():
        barrier.wait()
        return auth_client.post(f"/api/events/{event['id']}/publish", headers=h)

    def do_patch():
        barrier.wait()
        return auth_client.patch(
            f"/api/events/{event['id']}", json={"title": "Concurrent title"}, headers=h
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        p, e = pool.submit(do_publish), pool.submit(do_patch)
        published, edited = p.result(), e.result()
    assert published.status_code == 200
    assert edited.status_code in (200, 409)
    saved = auth_client.get(f"/api/events/{event['id']}").json()
    assert saved["status"] == "PUBLISHED"
    assert saved["title"] == (
        "Concurrent title" if edited.status_code == 200 else event["title"]
    )
    assert published.json()["title"] == saved["title"]


@pytest.mark.parametrize("offset,expected", [(-1, 409), (0, 409), (1, 200)])
def test_publish_start_strict_microsecond_boundary(
    auth_client, auth_database, offset, expected
):
    from datetime import timedelta

    login(auth_client)
    event = create(auth_client)
    start = datetime.fromisoformat("2026-10-04T12:00:00+00:00") + timedelta(
        microseconds=offset
    )
    with auth_database.begin() as db:
        db.execute(
            text("UPDATE events SET starts_at = :start WHERE id = :id"),
            {"start": start, "id": event["id"]},
        )
    assert publish(auth_client, event["id"]).status_code == expected


def test_publish_waits_for_lock_and_revalidates_committed_schedule(
    auth_client, auth_database
):
    from threading import Event as Signal
    from time import monotonic
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.common.errors import AppError
    from app.events.models import Event
    from app.events.service import publish_owned_event

    owner_id = UUID(login(auth_client))
    event = create(auth_client)
    pid_ready = Signal()
    worker_pid = []
    with Session(auth_database) as locked:
        row = locked.get(Event, UUID(event["id"]), with_for_update=True)
        assert row is not None
        blocker = locked.scalar(text("SELECT pg_backend_pid()"))

        def attempt():
            with Session(auth_database) as session:
                worker_pid.append(session.scalar(text("SELECT pg_backend_pid()")))
                pid_ready.set()
                with pytest.raises(AppError) as failure:
                    publish_owned_event(
                        session,
                        FixedClock(datetime.fromisoformat("2026-10-04T12:00:00+00:00")),
                        owner_id,
                        row.id,
                    )
                assert failure.value.code == "EVENT_NOT_PUBLISHABLE"

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(attempt)
            try:
                assert pid_ready.wait(5)
                deadline = monotonic() + 5
                with auth_database.connect() as monitor:
                    while monotonic() < deadline:
                        blockers = monitor.scalar(
                            text("SELECT pg_blocking_pids(:pid)"),
                            {"pid": worker_pid[0]},
                        )
                        if blocker in blockers:
                            break
                    else:
                        pytest.fail("Publish did not wait on the Event row lock")
                row.starts_at = datetime.fromisoformat("2026-10-04T12:00:00+00:00")
                locked.commit()
            finally:
                locked.rollback()
            future.result(timeout=5)
    assert auth_client.get(f"/api/events/{event['id']}").json()["status"] == "DRAFT"
