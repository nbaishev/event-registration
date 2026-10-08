from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event as Signal
from time import monotonic
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.clock import FixedClock
from app.common.errors import AppError
from app.events import repository as events
from app.events.models import Event
from app.events.schemas import EventPatchRequest
from app.events.service import patch_owned_event
from app.main import app
from app.notifications.repository import find_reminder_candidates
from app.notifications.service import deliver_confirmation, deliver_reminder
from app.notifications.transitions import get_transition_dispatcher
from app.registrations.models import Registration
from app.registrations.service import register_for_event, reset_state
from tests.integration.test_event_capacity import event_snapshot, owner_login
from tests.integration.test_event_draft_edit import patch
from tests.integration.test_event_registration import NOW
from tests.integration.test_registration_cancel import participants
from tests.integration.test_waitlist_promotion import snapshot


class Dispatcher:
    def __init__(self, callback=None):
        self.notices = []
        self.callback = callback

    def enqueue(self, notice):
        self.notices.append(notice)
        if self.callback:
            self.callback(notice)


def reschedule(db, event, body, dispatcher, session=None):
    def run(s):
        return patch_owned_event(
            s,
            FixedClock(NOW),
            UUID(event["owner_id"]),
            UUID(event["id"]),
            EventPatchRequest(**body),
            notification_dispatcher=dispatcher,
        )

    if session is not None:
        return run(session)
    with Session(db) as s:
        return run(s)


def test_http_snapshot_statuses_after_commit_and_enqueue_failure(
    auth_client, auth_database
):
    event, rows = participants(auth_client, auth_database, 3)
    with Session(auth_database) as s:
        cancelled = s.get(Registration, UUID(rows[2]["id"]))
        reset_state(cancelled, NOW)
        cancelled.status = "CANCELLED"
        cancelled.cancelled_at = NOW
        confirmed = s.get(Registration, UUID(rows[0]["id"]))
        confirmed.confirmation_email_sent_at = confirmed.reminder_sent_at = NOW
        s.commit()
    before = event_snapshot(auth_database, event["id"])
    registrations = snapshot(auth_database)

    observed = []

    def committed(notice):
        observed.append(event_snapshot(auth_database, event["id"]))
        if len(dispatcher.notices) == 1:
            raise RuntimeError("broker unavailable")

    dispatcher = Dispatcher(committed)
    app.dependency_overrides[get_transition_dispatcher] = lambda: dispatcher
    owner_login(auth_client)
    response = patch(auth_client, event["id"], {"timezone": "Asia/Bishkek"})
    assert response.status_code == 200
    assert len(observed) == 2
    assert all(
        saved["timezone"] == "Asia/Bishkek" and saved["schedule_updated_at"] == NOW
        for saved in observed
    )
    assert {n.recipient for n in dispatcher.notices} == {
        "p0@example.com",
        "p1@example.com",
    }
    assert all(
        n.starts_at == before["starts_at"] and n.timezone == "Asia/Bishkek"
        for n in dispatcher.notices
    )
    assert event_snapshot(auth_database, event["id"]) == before | {
        "timezone": "Asia/Bishkek",
        "updated_at": NOW,
        "schedule_updated_at": NOW,
    }
    assert snapshot(auth_database) == registrations
    assert (
        patch(auth_client, event["id"], {"timezone": "Asia/Bishkek"}).status_code == 200
    )
    assert len(dispatcher.notices) == 2


@pytest.mark.parametrize("failure", ["snapshot", "commit"])
def test_transaction_failure_never_dispatches(
    auth_client, auth_database, monkeypatch, failure
):
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
            reschedule(
                auth_database, event, {"timezone": "Asia/Bishkek"}, dispatcher, s
            )
        assert error.value.code == "SERVICE_UNAVAILABLE"
        assert s.get(Event, UUID(event["id"])).timezone == before["timezone"]
    assert dispatcher.notices == []
    assert event_snapshot(auth_database, event["id"]) == before


def test_two_transitions_keep_independent_dates_and_recipient_snapshots(
    auth_client, auth_database
):
    event, rows = participants(auth_client, auth_database, 2)
    dispatcher = Dispatcher()
    first = NOW + timedelta(days=3)
    second = NOW + timedelta(days=5)
    for starts in [first, second]:
        reschedule(
            auth_database,
            event,
            {"starts_at": starts, "ends_at": starts + timedelta(hours=2)},
            dispatcher,
        )
        if starts == first:
            with Session(auth_database) as s:
                s.get(User, UUID(rows[0]["user_id"])).email = "new@example.com"
                s.commit()
    assert [n.starts_at for n in dispatcher.notices].count(first) == 2
    assert [n.starts_at for n in dispatcher.notices].count(second) == 2
    assert {n.recipient for n in dispatcher.notices[:2]} == {
        "p0@example.com",
        "p1@example.com",
    }
    assert {n.recipient for n in dispatcher.notices[2:]} == {
        "new@example.com",
        "p1@example.com",
    }


def test_draft_guard_validation_and_no_email(auth_client, auth_database):
    event, _ = participants(auth_client, auth_database, 1)
    dispatcher = Dispatcher()
    app.dependency_overrides[get_transition_dispatcher] = lambda: dispatcher
    assert (
        patch(auth_client, event["id"], {"timezone": "UTC"}).json()["error"]["code"]
        == "EVENT_NOT_OWNER"
    )
    owner_login(auth_client)
    assert patch(auth_client, str(uuid4()), {"timezone": "UTC"}).status_code == 404
    for body in [
        {"starts_at": NOW.isoformat()},
        {"ends_at": NOW.isoformat()},
        {"timezone": "Invalid/Zone"},
        {"timezone": None},
        {"timezone": "UTC", "capacity": 1},
    ]:
        assert patch(auth_client, event["id"], body).status_code in (409, 422)
    with Session(auth_database) as s:
        s.get(Event, UUID(event["id"])).status = "DRAFT"
        s.commit()
    assert (
        patch(
            auth_client,
            event["id"],
            {"timezone": "Asia/Bishkek", "title": "Updated draft"},
        ).status_code
        == 200
    )
    assert dispatcher.notices == []
    with Session(auth_database) as s:
        s.get(Event, UUID(event["id"])).status = "CANCELLED"
        s.commit()
    assert (
        patch(auth_client, event["id"], {"timezone": "UTC"}).json()["error"]["code"]
        == "EVENT_CANCELLED"
    )


@pytest.mark.parametrize("sent", [False, True])
def test_reschedule_reminder_rules(auth_client, auth_database, sent):
    event, rows = participants(auth_client, auth_database, 1)
    with Session(auth_database) as s:
        row = s.get(Registration, UUID(rows[0]["id"]))
        row.confirmed_at = NOW - timedelta(days=2)
        if sent:
            row.reminder_sent_at = NOW - timedelta(hours=1)
        s.commit()
    dispatcher = Dispatcher()
    starts = NOW + timedelta(hours=23)
    reschedule(
        auth_database,
        event,
        {"starts_at": starts, "ends_at": starts + timedelta(hours=1)},
        dispatcher,
    )
    with Session(auth_database) as s:
        assert find_reminder_candidates(s, NOW) == []
    starts = NOW + timedelta(days=3)
    reschedule(
        auth_database,
        event,
        {"starts_at": starts, "ends_at": starts + timedelta(hours=1)},
        dispatcher,
    )
    with Session(auth_database) as s:
        assert find_reminder_candidates(s, starts - timedelta(hours=24)) == (
            [] if sent else [(UUID(event["id"]), UUID(rows[0]["id"]))]
        )
        assert s.get(Registration, UUID(rows[0]["id"])).reminder_sent_at == (
            NOW - timedelta(hours=1) if sent else None
        )


@pytest.mark.parametrize("competitor", ["register", "confirmation", "reminder"])
def test_reschedule_serializes_pending_operations(
    auth_client, auth_database, competitor
):
    event, rows = participants(auth_client, auth_database, 2)
    eid = UUID(event["id"])
    user = UUID(rows[1]["user_id"])
    if competitor == "register":
        with Session(auth_database) as s:
            s.delete(s.get(Registration, UUID(rows[1]["id"])))
            s.commit()
    if competitor == "reminder":
        with Session(auth_database) as s:
            current_event = s.get(Event, eid)
            current_event.starts_at = NOW + timedelta(hours=23)
            current_event.ends_at = NOW + timedelta(hours=25)
            current_event.schedule_updated_at = NOW - timedelta(days=2)
            s.get(Registration, UUID(rows[0]["id"])).confirmed_at = NOW - timedelta(
                days=2
            )
            s.commit()
            assert find_reminder_candidates(s, NOW) == [(eid, UUID(rows[0]["id"]))]
    messages = []

    class Sender:
        def send(self, message):
            messages.append(message)

    ready, pids = Signal(), []
    dispatcher = Dispatcher()
    with Session(auth_database) as locked:
        events.find_event_for_update(locked, eid)
        blocker = locked.scalar(text("SELECT pg_backend_pid()"))

        def compete():
            with Session(auth_database) as s:
                pids.append(s.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                if competitor == "register":
                    return register_for_event(s, FixedClock(NOW), user, eid).status
                delivery = (
                    deliver_confirmation
                    if competitor == "confirmation"
                    else deliver_reminder
                )
                return delivery(
                    s,
                    FixedClock(NOW),
                    Sender(),
                    eid,
                    UUID(rows[0]["id"]),
                    "https://example.com",
                )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(compete)
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
                        pytest.fail("Operation did not wait for Event lock")
                reschedule(
                    auth_database,
                    event,
                    {"timezone": "Asia/Bishkek"},
                    dispatcher,
                    locked,
                )
            finally:
                locked.rollback()
            result = future.result(timeout=5)
    if competitor == "register":
        assert result == "WAITLIST" and len(dispatcher.notices) == 1
    elif competitor == "confirmation":
        assert result is True and "Asia/Bishkek" in messages[0].body
    else:
        assert result is False and messages == []
