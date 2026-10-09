from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event as Signal
from time import monotonic
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.clock import FixedClock, get_clock
from app.common.errors import AppError
from app.events import repository as events
from app.events.models import Event
from app.events.service import cancel_owned_event
from app.main import app
from app.notifications.service import deliver_confirmation, deliver_reminder
from app.notifications.transitions import get_transition_dispatcher
from app.registrations.checkin import check_in
from app.registrations.models import Registration
from app.registrations.service import register_for_event, reset_state
from tests.integration.test_event_capacity import event_snapshot, owner_login
from tests.integration.test_event_draft_edit import headers, patch
from tests.integration.test_event_registration import NOW, post
from tests.integration.test_event_reschedule import Dispatcher
from tests.integration.test_registration_cancel import participants, sign_in
from tests.integration.test_waitlist_promotion import snapshot


def cancel(db, event, dispatcher, session=None):
    def run(s):
        return cancel_owned_event(
            s,
            FixedClock(NOW),
            UUID(event["owner_id"]),
            UUID(event["id"]),
            notification_dispatcher=dispatcher,
        )

    if session is not None:
        return run(session)
    with Session(db) as s:
        return run(s)


def http_cancel(client, eid):
    return client.post(f"/api/events/{eid}/cancel", headers=headers(client))


def test_api_snapshot_commit_failure_continues_and_preserves_history(
    auth_client, auth_database
):
    event, rows = participants(auth_client, auth_database, 3)
    with Session(auth_database) as s:
        row = s.get(Registration, UUID(rows[2]["id"]))
        reset_state(row, NOW)
        row.status, row.cancelled_at = "CANCELLED", NOW
        row = s.get(Registration, UUID(rows[0]["id"]))
        row.confirmation_email_sent_at = row.reminder_sent_at = NOW
        s.commit()
    before, history = (
        event_snapshot(auth_database, event["id"]),
        snapshot(auth_database),
    )
    observations = []

    def committed(notice):
        observations.append(event_snapshot(auth_database, event["id"]))
        if len(observations) == 1:
            raise RuntimeError("broker down")

    dispatcher = Dispatcher(committed)
    app.dependency_overrides[get_transition_dispatcher] = lambda: dispatcher
    assert (
        http_cancel(auth_client, event["id"]).json()["error"]["code"]
        == "EVENT_NOT_OWNER"
    )
    owner_login(auth_client)
    assert http_cancel(auth_client, str(uuid4())).status_code == 404
    response = http_cancel(auth_client, event["id"])
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    expected = before | {"status": "CANCELLED", "cancelled_at": NOW, "updated_at": NOW}
    assert observations == [expected, expected]
    assert {n.recipient for n in dispatcher.notices} == {
        "p0@example.com",
        "p1@example.com",
    }
    assert all(
        n.kind == "EVENT_CANCELLED" and n.starts_at == before["starts_at"]
        for n in dispatcher.notices
    )
    assert snapshot(auth_database) == history
    app.dependency_overrides[get_clock] = lambda: FixedClock(before["starts_at"])
    owner_login(auth_client)
    assert (
        http_cancel(auth_client, event["id"]).json()["error"]["code"]
        == "EVENT_CANCELLED"
    )
    assert (
        event_snapshot(auth_database, event["id"]) == expected
        and len(dispatcher.notices) == 2
    )
    assert (
        auth_client.get(f"/api/public/events/{event['slug']}").json()["status"]
        == "CANCELLED"
    )
    for body in [{"capacity": 2}, {"timezone": "UTC"}]:
        assert (
            patch(auth_client, event["id"], body).json()["error"]["code"]
            == "EVENT_CANCELLED"
        )
    result = auth_client.post(
        f"/api/events/{event['id']}/check-ins",
        headers=headers(auth_client),
        json={"ticket_code": rows[0]["ticket_code"]},
    )
    assert result.json()["error"]["code"] == "EVENT_CANCELLED"
    sign_in(auth_client, 2)
    assert post(auth_client, event).json()["error"]["code"] == "EVENT_CANCELLED"
    assert snapshot(auth_database) == history


@pytest.mark.parametrize("failure", ["snapshot", "commit"])
def test_rollback_no_enqueue(auth_client, auth_database, monkeypatch, failure):
    from app.events import service

    event, _ = participants(auth_client, auth_database, 2)
    before = event_snapshot(auth_database, event["id"])
    dispatcher = Dispatcher()

    def fail(*args):
        raise OperationalError("injected", {}, Exception("injected"))

    with Session(auth_database) as s:
        if failure == "snapshot":
            monkeypatch.setattr(service, "find_transition_recipients", fail)
        else:
            monkeypatch.setattr(s, "commit", fail)
        with pytest.raises(AppError) as error:
            cancel(auth_database, event, dispatcher, s)
        assert error.value.code == "SERVICE_UNAVAILABLE"
    assert (
        dispatcher.notices == []
        and event_snapshot(auth_database, event["id"]) == before
    )


def wait_for_block(db, blocker, pid):
    deadline = monotonic() + 5
    with db.connect() as monitor:
        while monotonic() < deadline:
            if blocker in monitor.scalar(
                text("SELECT pg_blocking_pids(:pid)"), {"pid": pid}
            ):
                return
    pytest.fail("Operation did not wait for Event lock")


def prepare_race(client, db):
    event, rows = participants(client, db, 2)
    with Session(db) as s:
        current = s.get(Event, UUID(event["id"]))
        current.starts_at, current.ends_at = (
            NOW + timedelta(hours=1),
            NOW + timedelta(hours=3),
        )
        current.schedule_updated_at = NOW - timedelta(days=2)
        s.get(Registration, UUID(rows[0]["id"])).confirmed_at = NOW - timedelta(days=2)
        s.commit()
    return event, rows


@pytest.mark.parametrize(
    "competitor", ["checkin", "register", "confirmation", "reminder"]
)
def test_cancellation_commits_before_pending_operation(
    auth_client, auth_database, competitor
):
    event, rows = prepare_race(auth_client, auth_database)
    eid, rid = UUID(event["id"]), UUID(rows[0]["id"])
    if competitor == "register":
        with Session(auth_database) as s:
            s.delete(s.get(Registration, UUID(rows[1]["id"])))
            s.commit()
    messages = []

    class Sender:
        def send(self, message):
            messages.append(message)

    ready, pids = Signal(), []
    with Session(auth_database) as locked:
        events.find_event_for_update(locked, eid)
        blocker = locked.scalar(text("SELECT pg_backend_pid()"))

        def compete():
            with Session(auth_database) as s:
                pids.append(s.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                try:
                    if competitor == "checkin":
                        return check_in(
                            s,
                            FixedClock(NOW),
                            UUID(event["owner_id"]),
                            eid,
                            rows[0]["ticket_code"].replace("-", ""),
                        )
                    if competitor == "register":
                        return register_for_event(
                            s, FixedClock(NOW), UUID(rows[1]["user_id"]), eid
                        )
                    delivery = (
                        deliver_confirmation
                        if competitor == "confirmation"
                        else deliver_reminder
                    )
                    return delivery(
                        s, FixedClock(NOW), Sender(), eid, rid, "https://example.com"
                    )
                except AppError as error:
                    return error.code

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(compete)
            try:
                assert ready.wait(5)
                wait_for_block(auth_database, blocker, pids[0])
                cancel(auth_database, event, Dispatcher(), locked)
            finally:
                locked.rollback()
            result = future.result(timeout=5)
    assert result == (
        "EVENT_CANCELLED" if competitor in {"checkin", "register"} else False
    )
    assert messages == []
    with Session(auth_database) as s:
        assert s.get(Registration, rid).checked_in_at is None


@pytest.mark.parametrize("first", ["checkin", "confirmation", "reminder"])
def test_shared_lock_operation_finishes_before_cancellation(
    auth_client, auth_database, first
):
    event, rows = prepare_race(auth_client, auth_database)
    eid, rid = UUID(event["id"]), UUID(rows[0]["id"])
    ready, pids, messages = Signal(), [], []

    class Sender:
        def send(self, message):
            messages.append(message)

    with Session(auth_database) as shared:
        events.find_event_for_share(shared, eid)
        blocker = shared.scalar(text("SELECT pg_backend_pid()"))

        def cancellation():
            with Session(auth_database) as s:
                pids.append(s.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                cancel(auth_database, event, Dispatcher(), s)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(cancellation)
            try:
                assert ready.wait(5)
                wait_for_block(auth_database, blocker, pids[0])
                if first == "checkin":
                    result = check_in(
                        shared,
                        FixedClock(NOW),
                        UUID(event["owner_id"]),
                        eid,
                        rows[0]["ticket_code"].replace("-", ""),
                    )
                    assert result.checked_in_at == NOW
                else:
                    delivery = (
                        deliver_confirmation
                        if first == "confirmation"
                        else deliver_reminder
                    )
                    assert (
                        delivery(
                            shared,
                            FixedClock(NOW),
                            Sender(),
                            eid,
                            rid,
                            "https://example.com",
                        )
                        is True
                    )
            finally:
                shared.rollback()
            future.result(timeout=5)
    with Session(auth_database) as s:
        assert s.get(Event, eid).status == "CANCELLED"
        row = s.get(Registration, rid)
        assert row.status == "CONFIRMED" and row.ticket_code is not None
        if first == "checkin":
            assert row.checked_in_at == NOW
        else:
            assert len(messages) == 1
            assert (
                row.confirmation_email_sent_at
                if first == "confirmation"
                else row.reminder_sent_at
            ) == NOW


def test_queued_notice_keeps_recipient_and_event_snapshot(auth_client, auth_database):
    from app.auth.models import User
    from app.notifications.rendering import render_transition_email

    event, rows = participants(auth_client, auth_database, 2)
    dispatcher = Dispatcher()
    cancel(auth_database, event, dispatcher)
    with Session(auth_database) as s:
        s.get(User, UUID(rows[0]["user_id"])).email = "later@example.com"
        row = s.get(Registration, UUID(rows[1]["id"]))
        reset_state(row, NOW)
        row.status, row.cancelled_at = "CANCELLED", NOW
        s.get(Event, UUID(event["id"])).title = "Later title"
        s.commit()
    mails = [
        render_transition_email(n, "https://example.com") for n in dispatcher.notices
    ]
    assert {mail.recipient for mail in mails} == {"p0@example.com", "p1@example.com"}
    assert all(
        "Later title" not in mail.body and event["title"] in mail.body for mail in mails
    )
