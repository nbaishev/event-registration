import asyncio
import json
import shlex
import socket
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.clock import FixedClock
from app.common.errors import AppError
from app.events.broadcaster import StatsBroadcaster
from app.events.schemas import EventPatchRequest
from app.events.service import patch_owned_event
from app.main import app
from app.registrations.checkin import check_in
from app.registrations.service import cancel_registration, register_for_event
from tests.integration.test_checkin import sign_in_owner
from tests.integration.test_event_draft_edit import create, login
from tests.integration.test_event_registration import NOW, post, setup_event


@asynccontextmanager
async def live_server():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 5)
        finally:
            sock.close()


async def wait_until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.01)


def test_stream_transport_releases_db_and_unsubscribes(
    auth_client, auth_database, monkeypatch
):
    from app.events import stream

    monkeypatch.setattr(stream, "get_engine", lambda: auth_database)
    owner, event = setup_event(auth_client, auth_database)
    auth_client.cookies.clear()
    login(auth_client, "participant@example.com")
    participant_cookies = dict(auth_client.cookies)
    sign_in_owner(auth_client)
    cookies = dict(auth_client.cookies)
    auth_client.cookies.clear()
    auth_client.cookies.update(participant_cookies)
    event_id = UUID(event["id"])

    async def scenario():
        async with (
            live_server() as url,
            httpx.AsyncClient(base_url=url, cookies=cookies, timeout=3) as client,
        ):
            broadcaster = app.state.stats_broadcaster
            async with client.stream(
                "GET", f"/api/events/{event_id}/stats/stream"
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                assert response.headers["cache-control"] == "no-store"
                # Headers arrive before a business signal; auth connection is free.
                assert auth_database.pool.checkedout() == 0
                assert len(broadcaster._subscribers[event_id]) == 1

                registered = await asyncio.to_thread(post, auth_client, event)
                assert registered.status_code == 201
                lines = response.aiter_lines()
                assert await anext(lines) == "event: stats_changed"
                assert await anext(lines) == "data: {}"
                assert await anext(lines) == ""
                with Session(auth_database) as reader:
                    assert (
                        reader.scalar(
                            text(
                                "SELECT count(*) FROM registrations "
                                "WHERE status='CONFIRMED'"
                            )
                        )
                        == 1
                    )
            await wait_until(lambda: event_id not in broadcaster._subscribers)

    asyncio.run(scenario())


@pytest.mark.parametrize("lifecycle", ["DRAFT", "PUBLISHED", "FINISHED", "CANCELLED"])
def test_stream_access_lifecycle(auth_client, auth_database, monkeypatch, lifecycle):
    from app.events import stream

    monkeypatch.setattr(stream, "get_engine", lambda: auth_database)
    login(auth_client)
    event = create(auth_client)
    event_id = UUID(event["id"])
    if lifecycle != "DRAFT":
        with auth_database.begin() as conn:
            conn.execute(
                text(
                    "UPDATE events SET status=:status, starts_at=:start, "
                    "ends_at=:end WHERE id=:id"
                ),
                {
                    "status": "PUBLISHED" if lifecycle == "FINISHED" else lifecycle,
                    "start": NOW - timedelta(hours=1),
                    "end": NOW if lifecycle == "FINISHED" else NOW + timedelta(hours=1),
                    "id": event_id,
                },
            )
    cookies = dict(auth_client.cookies)
    auth_client.cookies.clear()
    login(auth_client, "outsider@example.com")
    outsider = dict(auth_client.cookies)

    async def scenario():
        async with (
            live_server() as url,
            httpx.AsyncClient(base_url=url, timeout=3) as client,
        ):
            path = f"/api/events/{event_id}/stats/stream"
            for cookie, target, status, code in [
                ({}, path, 401, "AUTH_REQUIRED"),
                (outsider, path, 403, "EVENT_NOT_OWNER"),
                (
                    cookies,
                    f"/api/events/{uuid4()}/stats/stream",
                    404,
                    "EVENT_NOT_FOUND",
                ),
            ]:
                client.cookies.clear()
                client.cookies.update(cookie)
                response = await client.get(target)
                assert response.status_code == status
                assert response.json()["error"]["code"] == code
                assert response.headers["cache-control"] == "no-store"
            client.cookies.clear()
            client.cookies.update(cookies)
            async with client.stream("GET", path) as response:
                assert response.status_code == (409 if lifecycle == "DRAFT" else 200)
                if lifecycle == "DRAFT":
                    await response.aread()
                    assert response.json()["error"]["code"] == "EVENT_NOT_PUBLISHED"
                assert auth_database.pool.checkedout() == 0

    asyncio.run(scenario())


def test_postcommit_mutations_and_coalesced_promotions(auth_client, auth_database):
    owner, event = setup_event(auth_client, auth_database)
    participants = []
    for index in range(3):
        auth_client.cookies.clear()
        participants.append(UUID(login(auth_client, f"p{index}@example.com")))
    event_id, owner_id = UUID(event["id"]), UUID(owner)

    published_snapshots = []

    class ObservedBroadcaster(StatsBroadcaster):
        def publish(self, event_id):
            with Session(auth_database) as reader:
                snapshot = reader.execute(
                    text(
                        "SELECT count(*) FILTER (WHERE status='CONFIRMED'), "
                        "count(*) FILTER (WHERE status='WAITLIST'), "
                        "count(*) FILTER (WHERE checked_in_at IS NOT NULL) "
                        "FROM registrations"
                    )
                ).one()
                published_snapshots.append(tuple(snapshot))
            super().publish(event_id)

    async def scenario():
        broadcaster = ObservedBroadcaster()
        broadcaster.startup()
        queue = broadcaster.subscribe(event_id)
        unrelated = broadcaster.subscribe(uuid4())

        async def mutation(operation, expected):
            def run():
                with Session(auth_database) as session:
                    return operation(session)

            result = await asyncio.to_thread(run)
            assert await asyncio.wait_for(queue.get(), 3) is None
            assert queue.empty() and unrelated.empty()
            assert published_snapshots.pop(0) == expected
            assert not published_snapshots
            with Session(auth_database) as reader:
                counts = reader.execute(
                    text(
                        "SELECT count(*) FILTER (WHERE status='CONFIRMED'), "
                        "count(*) FILTER (WHERE status='WAITLIST'), "
                        "count(*) FILTER (WHERE checked_in_at IS NOT NULL) "
                        "FROM registrations"
                    )
                ).one()
                assert tuple(counts) == expected
            return result

        try:
            for index, user in enumerate(participants):
                await mutation(
                    lambda s, user=user: register_for_event(
                        s, FixedClock(NOW), user, event_id, broadcaster=broadcaster
                    ),
                    (1, index, 0),
                )
            await mutation(
                lambda s: cancel_registration(
                    s,
                    FixedClock(NOW),
                    participants[0],
                    event_id,
                    broadcaster=broadcaster,
                ),
                (1, 1, 0),
            )
            await mutation(
                lambda s: register_for_event(
                    s,
                    FixedClock(NOW),
                    participants[0],
                    event_id,
                    broadcaster=broadcaster,
                ),
                (1, 2, 0),
            )
            await mutation(
                lambda s: patch_owned_event(
                    s,
                    FixedClock(NOW),
                    owner_id,
                    event_id,
                    EventPatchRequest(capacity=3),
                    broadcaster=broadcaster,
                ),
                (3, 0, 0),
            )
            with auth_database.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE events SET starts_at=:start, ends_at=:end WHERE id=:id"
                    ),
                    {
                        "id": event_id,
                        "start": NOW + timedelta(hours=1),
                        "end": NOW + timedelta(hours=2),
                    },
                )
                ticket = conn.scalar(
                    text("SELECT ticket_code FROM registrations WHERE user_id=:id"),
                    {"id": participants[1]},
                )
            await mutation(
                lambda s: check_in(
                    s,
                    FixedClock(NOW),
                    owner_id,
                    event_id,
                    ticket,
                    broadcaster=broadcaster,
                ),
                (3, 0, 1),
            )
        finally:
            broadcaster.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "operation", ["register", "cancel", "capacity", "checkin", "noop"]
)
def test_rollback_and_noop_are_silent(
    auth_client, auth_database, monkeypatch, operation
):
    owner, event = setup_event(auth_client, auth_database)
    auth_client.cookies.clear()
    user = UUID(login(auth_client, "p@example.com"))
    event_id = UUID(event["id"])
    with Session(auth_database) as session:
        row = register_for_event(session, FixedClock(NOW), user, event_id)
    if operation == "checkin":
        with auth_database.begin() as conn:
            conn.execute(
                text("UPDATE events SET starts_at=:start, ends_at=:end WHERE id=:id"),
                {
                    "id": event_id,
                    "start": NOW + timedelta(hours=1),
                    "end": NOW + timedelta(hours=2),
                },
            )
    if operation == "register":
        with Session(auth_database) as session:
            cancel_registration(session, FixedClock(NOW), user, event_id)

    async def scenario():
        broadcaster = StatsBroadcaster()
        broadcaster.startup()
        queue = broadcaster.subscribe(event_id)

        def run():
            with Session(auth_database) as session:
                if operation != "noop":

                    def fail():
                        raise OperationalError("commit failed", {}, Exception())

                    monkeypatch.setattr(session, "commit", fail)

                def execute():
                    if operation == "register":
                        register_for_event(
                            session,
                            FixedClock(NOW),
                            user,
                            event_id,
                            broadcaster=broadcaster,
                        )
                    elif operation == "cancel":
                        cancel_registration(
                            session,
                            FixedClock(NOW),
                            user,
                            event_id,
                            broadcaster=broadcaster,
                        )
                    elif operation == "checkin":
                        check_in(
                            session,
                            FixedClock(NOW),
                            UUID(owner),
                            event_id,
                            row.ticket_code.replace("-", ""),
                            broadcaster=broadcaster,
                        )
                    else:
                        patch_owned_event(
                            session,
                            FixedClock(NOW),
                            UUID(owner),
                            event_id,
                            EventPatchRequest(capacity=1 if operation == "noop" else 3),
                            broadcaster=broadcaster,
                        )

                if operation == "noop":
                    execute()
                else:
                    with pytest.raises(AppError) as error:
                        execute()
                    assert error.value.code == "SERVICE_UNAVAILABLE"

        try:
            await asyncio.to_thread(run)
            assert queue.empty()
            with Session(auth_database) as reader:
                assert (
                    reader.scalar(
                        text("SELECT capacity FROM events WHERE id=:id"),
                        {"id": event_id},
                    )
                    == 1
                )
                assert (
                    reader.scalar(
                        text(
                            "SELECT checked_in_at FROM registrations WHERE user_id=:id"
                        ),
                        {"id": user},
                    )
                    is None
                )
                assert reader.scalar(
                    text("SELECT status FROM registrations WHERE user_id=:id"),
                    {"id": user},
                ) == ("CANCELLED" if operation == "register" else "CONFIRMED")
        finally:
            broadcaster.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["register", "cancel", "capacity", "checkin"])
def test_publish_failure_preserves_committed_success(
    auth_client, auth_database, operation, caplog
):
    owner, event = setup_event(auth_client, auth_database, capacity=2)
    auth_client.cookies.clear()
    user = UUID(login(auth_client, "p@example.com"))
    event_id = UUID(event["id"])
    with Session(auth_database) as session:
        if operation != "register":
            row = register_for_event(session, FixedClock(NOW), user, event_id)
    if operation == "checkin":
        with auth_database.begin() as conn:
            conn.execute(
                text("UPDATE events SET starts_at=:start, ends_at=:end WHERE id=:id"),
                {
                    "id": event_id,
                    "start": NOW + timedelta(hours=1),
                    "end": NOW + timedelta(hours=2),
                },
            )

    class BrokenBroadcaster(StatsBroadcaster):
        def publish(self, event_id):
            raise RuntimeError("participant diagnostic must not be logged")

    with Session(auth_database) as session:
        broadcaster = BrokenBroadcaster()
        if operation == "register":
            response = register_for_event(
                session, FixedClock(NOW), user, event_id, broadcaster=broadcaster
            )
            assert response.status == "CONFIRMED"
        elif operation == "cancel":
            response = cancel_registration(
                session, FixedClock(NOW), user, event_id, broadcaster=broadcaster
            )
            assert response.status == "CANCELLED"
        elif operation == "capacity":
            patch_owned_event(
                session,
                FixedClock(NOW),
                UUID(owner),
                event_id,
                EventPatchRequest(capacity=1),
                broadcaster=broadcaster,
            )
        else:
            check_in(
                session,
                FixedClock(NOW),
                UUID(owner),
                event_id,
                row.ticket_code.replace("-", ""),
                broadcaster=broadcaster,
            )
    with Session(auth_database) as reader:
        assert reader.scalar(
            text("SELECT status FROM registrations WHERE user_id=:id"), {"id": user}
        ) == ("CANCELLED" if operation == "cancel" else "CONFIRMED")
        assert reader.scalar(
            text("SELECT capacity FROM events WHERE id=:id"), {"id": event_id}
        ) == (1 if operation == "capacity" else 2)
        checked_in = reader.scalar(
            text("SELECT checked_in_at FROM registrations WHERE user_id=:id"),
            {"id": user},
        )
        assert (checked_in is not None) == (operation == "checkin")
    assert "Statistics notification failed" in caplog.text
    assert "participant diagnostic" not in caplog.text


def test_deployed_server_shutdown_with_open_stream(
    auth_client, auth_database, monkeypatch
):
    from app.events import stream

    monkeypatch.setattr(stream, "get_engine", lambda: auth_database)
    setup_event(auth_client, auth_database)
    event_id = auth_client.get("/api/events/mine").json()[0]["id"]
    cookies = dict(auth_client.cookies)
    # Exercise the real deployed command's Uvicorn options, not test-only config.
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    command = next(
        line for line in dockerfile.read_text().splitlines() if line.startswith("CMD ")
    )
    args = shlex.split(json.loads(command[4:])[2].split("exec uvicorn ", 1)[1])
    from uvicorn.main import main as uvicorn_cli

    options = uvicorn_cli.make_context("uvicorn", args).params
    config = uvicorn.Config(
        app,
        log_level="error",
        lifespan="on",
        workers=options["workers"],
        timeout_graceful_shutdown=options["timeout_graceful_shutdown"],
    )

    async def scenario():
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            await wait_until(lambda: server.started)
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{sock.getsockname()[1]}",
                cookies=cookies,
                timeout=3,
            ) as client:
                async with client.stream(
                    "GET", f"/api/events/{event_id}/stats/stream"
                ) as response:
                    assert response.status_code == 200
                    broadcaster = app.state.stats_broadcaster
                    assert broadcaster._subscribers
                    server.should_exit = True
                    # Client stays connected throughout drain + lifespan shutdown.
                    done, _ = await asyncio.wait({task}, timeout=7)
                    assert task in done, "Server shutdown hung with an open SSE stream"
                    await task
                    assert broadcaster.closed
                    assert not broadcaster._subscribers
                    assert auth_database.pool.checkedout() == 0
        finally:
            server.should_exit = True
            server.force_exit = True
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            sock.close()

    asyncio.run(scenario())
